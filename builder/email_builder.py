"""Orchestrator: wires `.eml` parse → AI extract → render → create SFMC asset.

Public API
----------
* `parse_only(source) -> SupportNotesData` — runs parser + extractor, returns
  the structured slot data for the UI to display and let the user edit.
* `render_html(data) -> dict` — turns `SupportNotesData` into a fully-rendered
  HTML email document (the SFMC template with all slot divs replaced by
  their rendered HTML, plus `lang="..."` set correctly on `<html>`).
* `create(data, *, dry_run=False) -> dict` — full create flow: render,
  optionally call SFMC.

The Streamlit UI uses `parse_only` for the upload step and `create` for the
final "🚀 Create email in SFMC" button.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, IO, Optional, Union

from builder import (
    ai_extractor,
    eml_parser,
    language_config,
    sfmc_client,
    slot_renderer,
)
from builder.models import SupportNotesData

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "support-notes-template.html"


# ---------------------------------------------------------------------------
# Step 1 — parse + extract
# ---------------------------------------------------------------------------

def parse_only(
    source: Union[str, Path, bytes, IO[bytes]],
    *,
    language: str | None = None,
) -> tuple[SupportNotesData, Optional[str]]:
    """Parse a `.eml` request and extract structured slot data.

    Returns ``(data, ai_error)`` — see ``ai_extractor.extract`` for details.
    """
    parsed = eml_parser.parse(source)
    return ai_extractor.extract(parsed, language=language)


# ---------------------------------------------------------------------------
# Step 2 — render the full HTML email
# ---------------------------------------------------------------------------

# Match a single slot div, allowing `data-key`, `data-type`, and optionally
# `data-label` attributes in any order.
_SLOT_DIV_RE = re.compile(
    r'<div\b(?=[^>]*\bdata-type="slot")(?=[^>]*\bdata-key="(?P<key>[^"]+)")[^>]*>\s*</div>',
    re.IGNORECASE,
)


def render_html(data: SupportNotesData) -> Dict[str, Any]:
    """Render `SupportNotesData` to a fully-rendered HTML email.

    Returns a dict::

        {
            "html":         <full SFMC-template-with-slots-filled HTML>,
            "subject":      <localised subject line>,
            "preheader":    <preheader text>,
            "name":         <SFMC asset name we'd use, e.g. 'Tessent 지원 노트 - 2026년 5월'>,
            "slots":        <dict[slot_key, html] — for debugging>,
            "placeholders": <list of slot keys still containing TODO markers>,
        }
    """
    cfg = language_config.get(data.language)

    # 1) Render each slot's HTML
    slot_html = slot_renderer.render_slots(data)
    placeholders = slot_renderer.has_placeholders(slot_html)

    # 2) Load template, set <html lang="…"> for the language
    raw = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = re.sub(
        r'(<html\b[^>]*?\blang=)"[^"]*"',
        rf'\1"{cfg.html_lang}"',
        raw,
        count=1,
    )

    # 3) Replace each slot div with its rendered HTML.
    def _sub(m: re.Match) -> str:
        key = m.group("key")
        # The 'preheader' slot is HTML-commented out in the template; the real
        # preheader is set on SFMC asset metadata.
        if key == "preheader":
            text = data.preheader.strip()
            return text or ""  # silent no-op if empty
        return slot_html.get(key, m.group(0))  # leave untouched if not rendered

    html = _SLOT_DIV_RE.sub(_sub, html)

    # 4) Subject + asset name
    subject = _build_subject(data, cfg)
    asset_name = subject  # SFMC asset name = subject (no [TEST] prefix)

    return {
        "html": html,
        "subject": subject,
        "preheader": data.preheader.strip(),
        "name": asset_name,
        "slots": slot_html,
        "placeholders": placeholders,
    }


def _build_text_version(data: SupportNotesData, subject: str) -> str:
    """Build the plain-text view required by CAN-SPAM for every SFMC send."""
    def _strip(s: str) -> str:
        return re.sub(r"<[^>]+>", " ", s).strip()

    lines: list[str] = [subject, ""]
    if data.preheader:
        lines += [data.preheader, ""]

    for section in (data.section1, data.section2):
        if section.quote:
            lines += [section.quote, ""]
        if section.editorial_html:
            lines += [_strip(section.editorial_html), ""]
        for art in section.left_articles + section.right_articles:
            if art.label:
                lines += [f"{art.label}  {art.url}".strip(), ""]

    for web in data.upcoming_webinars:
        if web.title:
            lines += [web.title, ""]

    for comp in data.latest_release.components:
        if comp.label:
            lines.append(f"{comp.label}  {comp.url}".strip())
    lines.append("")

    from builder import static_slots as _ss
    _lang_code = _ss._LANG_UNSUB_CODE.get(data.language, "EN")
    _unsub_url = _ss._UNSUB_BASE + _lang_code
    lines += [
        "--",
        "This email was sent to: %%emailaddr%%",
        "%%Member_Busname%%",
        "%%Member_Addr%% %%Member_City%%, %%Member_State%%, %%Member_PostalCode%%, %%Member_Country%%",
        "",
        f"Update preferences: {_ss._PROFILE_URL}",
        f"Unsubscribe: {_unsub_url}",
        "",
        "© 2026 Siemens Digital Industries Software",
    ]
    return "\n".join(lines)


def _build_subject(data: SupportNotesData, cfg: language_config.LanguageConfig) -> str:
    """Format the subject string per language."""
    en_month_names = ["", "January", "February", "March", "April", "May", "June",
                      "July", "August", "September", "October", "November", "December"]
    fmt_kwargs = {
        "product": data.product,
        "year": data.year,
        "month": data.month,
        "month_name": en_month_names[data.month] if 1 <= data.month <= 12 else "",
    }
    return cfg.subject_template.format(**fmt_kwargs)


# ---------------------------------------------------------------------------
# Step 3 — create the SFMC asset
# ---------------------------------------------------------------------------

def create(data: SupportNotesData, *, dry_run: bool = False) -> Dict[str, Any]:
    """Render `SupportNotesData` and (unless dry-run) create the email asset
    in the per-language SFMC folder.

    Returns the same shape as `render_html` plus, on a real run, an `id`
    field holding the new SFMC asset ID.
    """
    cfg = language_config.get(data.language)
    rendered = render_html(data)

    if dry_run:
        rendered["dry_run"] = True
        return rendered

    folder_id = language_config.email_folder_id(cfg)
    template_id = language_config.template_id(cfg)

    asset = sfmc_client.create_html_email(
        name=rendered["name"],
        subject=rendered["subject"],
        preheader=rendered["preheader"],
        html=rendered["html"],
        text=_build_text_version(data, rendered["subject"]),
        folder_id=folder_id,
        template_id=template_id,
    )

    rendered["id"] = asset.id
    rendered["customer_key"] = asset.customer_key
    return rendered
