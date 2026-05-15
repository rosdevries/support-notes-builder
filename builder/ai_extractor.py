"""AI-assisted extraction of Support Notes content from a parsed `.eml`.

Given a `ParsedEml` (preview HTML + editor notes), call Claude Haiku to
produce structured slot data matching `SupportNotesData`.  The model is
prompted to extract content verbatim — it never translates or paraphrases.

If `ANTHROPIC_API_KEY` is not configured the call falls back to a heuristic
HTML-structure parse that gets the obvious structural fields right
(headline, speakers, quotes, KBAs) without any AI.  This means the app
keeps working in environments where the key isn't set, with the user just
doing more editing in the UI.

Public entry point
------------------
``extract(parsed, *, language) -> (SupportNotesData, Optional[str])``
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from pathlib import Path
from typing import Optional

from builder import eml_parser
from builder.models import (
    Article,
    EditorialSection,
    ParsedEml,
    ReleaseComponent,
    ReleaseHighlight,
    Speaker,
    SupportNotesData,
    WebinarHighlight,
)

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "extract_slots.txt"
_MODEL_ID = "claude-haiku-4-5-20251001"

# Use the OS system certificate store so corporate TLS-inspection proxies work.
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass  # truststore not installed — fall back to certifi bundle


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract(parsed: ParsedEml, *, language: Optional[str] = None) -> tuple[SupportNotesData, Optional[str]]:
    """Extract structured slot data from a parsed .eml.

    Returns ``(data, ai_error)`` where ``ai_error`` is ``None`` on success or a
    human-readable message when the AI call fails and the heuristic fallback was
    used instead.  The caller should surface ``ai_error`` as a warning so the
    user knows why fields are empty, without blocking the rest of the workflow.

    Strategy:
      * Always derive product / language / year / month from the .eml
        Subject header.
      * If `ANTHROPIC_API_KEY` is set, call Claude to fill the rich
        editorial fields. On failure, fall back to heuristic and return the
        error.  Otherwise use the heuristic from the start.
    """
    subject_meta = eml_parser.parse_subject(parsed.subject_header)
    product = subject_meta["product"]
    detected_lang = subject_meta["language"]
    year = subject_meta["year"]
    month = subject_meta["month"]

    if language and language != detected_lang:
        # Caller forced a language different from what the subject implies.
        # Honour the override but log it via the data model — we never throw.
        pass
    final_language = language or detected_lang

    ai_error: Optional[str] = None
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        try:
            data = _ai_extract(parsed)
        except Exception as exc:
            ai_error = _friendly_ai_error(exc)
            data = _heuristic_extract(parsed)
    else:
        data = _heuristic_extract(parsed)

    # Fill in the metadata fields from subject parsing.  These take priority
    # over whatever the model returned, since the subject is unambiguous.
    data.product = product
    data.language = final_language
    data.year = year
    data.month = month

    return data, ai_error


def _friendly_ai_error(exc: Exception) -> str:
    """Return a user-friendly error message for a failed AI extraction call."""
    msg = str(exc)
    low = msg.lower()
    if "ssl" in low or "certificate" in low or "verify" in low:
        return (
            "AI extraction failed: SSL certificate error — likely a corporate network proxy. "
            "Fields are empty; fill them in manually. "
            f"(Detail: {msg})"
        )
    if "connection" in low or "connect" in low or "network" in low or "timeout" in low:
        return (
            "AI extraction failed: could not reach the Anthropic API. "
            "Check your network connection or proxy settings. "
            f"(Detail: {msg})"
        )
    if "json" in low or "non-json" in low:
        return f"AI extraction failed: model returned invalid JSON. (Detail: {msg})"
    return f"AI extraction failed: {msg}"


# ---------------------------------------------------------------------------
# AI path
# ---------------------------------------------------------------------------

_SAFELINKS_RE = re.compile(
    r'https://[a-z0-9-]+\.safelinks\.protection\.outlook\.com/\?url=([^&"<>\s]+)[^"<>\s]*',
    re.IGNORECASE,
)

# SFMC click-tracking hostnames — URLs that redirect to real content but
# encode no recoverable destination for the AI.
_SFMC_TRACKING_HOSTS = re.compile(
    r'https?://cl\.s\d+\.exct\.net[^"<>\s]*',
    re.IGNORECASE,
)

# Anchors whose title starts with "Latest Release" — these are the download
# links for release components.  Their originalsrc value IS the correct URL.
_RELEASE_ANCHOR_RE = re.compile(
    r'(<a\b[^>]*?\btitle="Latest Release[^"]*"[^>]*>)',
    re.IGNORECASE | re.DOTALL,
)
_ORIGINALSRC_ATTR_RE = re.compile(r'\boriginalsrc="([^"]*)"', re.IGNORECASE)

# Microsoft Word / Outlook HTML artefacts that add noise without value.
_MSO_TAG_RE = re.compile(r'</?o:[^>]*>', re.IGNORECASE)
_MSO_STYLE_RE = re.compile(r'\bmso-[a-zA-Z-]+\s*:[^;"\'>]+;?', re.IGNORECASE)
_MSO_CLASS_RE = re.compile(r'\bclass="[^"]*Mso[^"]*"', re.IGNORECASE)
_MSO_XMLNS_RE = re.compile(r'\bxmlns:[ovwx]="[^"]*"', re.IGNORECASE)
_MULTI_SPACE_RE = re.compile(r'[ \t]{2,}')
# Entire <head> block — Word reply emails carry thousands of chars of CSS/XML
# that the AI should never see.
_HTML_HEAD_RE = re.compile(r'<head\b[^>]*>.*?</head\s*>', re.IGNORECASE | re.DOTALL)


def _recover_release_urls(html: str) -> str:
    """Swap #sfmc-tracking back to originalsrc for 'Latest Release' anchors only.

    All other originalsrc attributes are stripped so the AI never sees an
    SFMC tracking URL for non-release links (webinar series, article links, etc).
    """
    def _fix_anchor(m: re.Match) -> str:
        tag = m.group(1)
        src = _ORIGINALSRC_ATTR_RE.search(tag)
        if src and src.group(1):
            tag = tag.replace('href="#sfmc-tracking"', f'href="{src.group(1)}"')
        return tag
    html = _RELEASE_ANCHOR_RE.sub(_fix_anchor, html)
    # Strip all remaining originalsrc attributes (non-release links keep sentinel).
    html = _ORIGINALSRC_ATTR_RE.sub('', html)
    return html


def _unwrap_safelinks(html: str) -> str:
    """Replace Outlook SafeLinks wrappers with the original URL.

    Order matters:
    1. Unwrap SafeLinks hrefs (SFMC tracking → sentinel, real URLs → kept).
    2. Recover release component URLs from still-intact ``originalsrc`` attrs.
    3. Strip all remaining SFMC tracking URLs (including now-redundant originalsrc).
    """
    def _replace(m: re.Match) -> str:
        try:
            inner = urllib.parse.unquote(m.group(1))
            if _SFMC_TRACKING_HOSTS.match(inner):
                return "#sfmc-tracking"
            return inner
        except Exception:
            return m.group(0)
    html = _SAFELINKS_RE.sub(_replace, html)
    # Restore real URLs for 'Latest Release' anchors from originalsrc, then
    # clear all originalsrc attrs.  After this step every SFMC tracking URL
    # remaining in an href belongs to a release component and should be kept.
    html = _recover_release_urls(html)
    return html


def _clean_word_html(html: str) -> str:
    """Strip Microsoft Word / Outlook HTML noise before sending to the AI.

    Word-generated (``Microsoft Word 15 (filtered medium)``) Outlook emails
    contain thousands of ``mso-*`` inline styles, ``<o:p>`` pseudo-paragraphs,
    and ``MsoNormal`` class names that obscure the actual content.  Stripping
    them reduces the HTML size by 20-30 % and makes it far easier for the AI
    to locate editorial text, speaker names, and structure.
    """
    html = _HTML_HEAD_RE.sub('', html)      # <head>…</head> (Word CSS/XML dumps)
    html = _MSO_TAG_RE.sub('', html)       # <o:p>, </o:p>, <o:shapedefaults …/>
    html = _MSO_XMLNS_RE.sub('', html)     # xmlns:o="…" xmlns:v="…" etc.
    html = _MSO_STYLE_RE.sub('', html)     # mso-line-height-rule:exactly; etc.
    html = _MSO_CLASS_RE.sub('', html)     # class="MsoNormal"
    html = _MULTI_SPACE_RE.sub(' ', html)  # collapse whitespace runs
    return html


def _ai_extract(parsed: ParsedEml) -> SupportNotesData:
    """Call Claude Haiku to map the .eml into structured slot data."""
    from anthropic import Anthropic

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")

    raw_preview = _clean_word_html(_unwrap_safelinks(parsed.preview_html)).strip()
    if not raw_preview:
        preview_block = (
            "(none — this is a reply-style request with no inline email mockup; "
            "extract ALL content from EDITOR_NOTES instead)"
        )
    else:
        preview_block = raw_preview

    user_msg = (
        "EDITOR_NOTES (HTML, may include images and tables of EN/KR URL pairs):\n"
        + _clean_word_html(_unwrap_safelinks(parsed.editor_notes_html or "(none)"))
        + "\n\n=========================\n\n"
        + "EMAIL_PREVIEW (HTML — the mock-up of the final email):\n"
        + preview_block
    )

    msg = client.messages.create(
        model=_MODEL_ID,
        max_tokens=8192,
        system=system_prompt,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()

    # Strip ```json fences if the model added them despite instructions.
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"\s*```\s*$", "", raw)

    try:
        d = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"AI extractor returned non-JSON: {e}\nFirst 400 chars:\n{raw[:400]}") from e

    return _data_from_ai_dict(d)


def _data_from_ai_dict(d: dict) -> SupportNotesData:
    """Map the AI's loose JSON into a strict `SupportNotesData`.

    Tolerant of missing fields — we'd rather render with placeholders
    the user can edit than blow up.
    """
    def _articles(lst) -> list[Article]:
        return [
            Article(label=a.get("label") or "", url=a.get("url") or "")
            for a in (lst or [])
        ]

    def _section(node: dict | None) -> EditorialSection:
        node = node or {}
        spk = node.get("speaker") or {}
        return EditorialSection(
            quote=node.get("quote") or "",
            editorial_html=node.get("editorial_html") or "",
            speaker=Speaker(
                name=spk.get("name") or "",
                title=spk.get("title") or "Applications Engineer",
                photo_url="",  # filled in later, after user uploads / SFMC lookup
            ),
            left_articles=_articles(node.get("left_articles")),
            right_articles=_articles(node.get("right_articles")),
        )

    rel_node = d.get("latest_release") or {}
    components = [
        ReleaseComponent(label=c.get("label") or "", url=c.get("url") or "")
        for c in (rel_node.get("components") or [])
    ]

    # Support both new list form and old singular form from the AI
    raw_webinars = d.get("upcoming_webinars") or []
    if not raw_webinars and d.get("upcoming_webinar"):
        raw_webinars = [d["upcoming_webinar"]]
    webinars = [
        WebinarHighlight(
            date_label=w.get("date_label") or "",
            title=w.get("title") or "",
            url=w.get("url") or "",
        )
        for w in raw_webinars
    ]

    return SupportNotesData(
        # product/language/year/month filled by extract() from subject
        header_title=d.get("header_title") or "",
        header_strapline=d.get("header_strapline") or "",
        subscribe_url=d.get("subscribe_url") or "",
        section1=_section(d.get("section1")),
        section2=_section(d.get("section2")),
        upcoming_webinars=webinars,
        webinar_series_url=d.get("webinar_series_url") or "",
        webinar_header_html=d.get("webinar_header_html") or "",
        promo_block_html=d.get("promo_block_html") or "",
        footnote_html=d.get("footnote_html") or "",
        latest_release=ReleaseHighlight(components=components),
        preheader=d.get("preheader") or "",
    )


# ---------------------------------------------------------------------------
# Heuristic fallback
# ---------------------------------------------------------------------------

def _heuristic_extract(parsed: ParsedEml) -> SupportNotesData:
    """Best-effort heuristic parse — gets the obvious bits without AI.

    Used when ANTHROPIC_API_KEY is not set or the AI call fails.  This is
    intentionally minimal: it derives product / language / year / month from
    the subject (which is unambiguous) and leaves rich editorial fields
    blank for the user to fill in via the Streamlit UI.

    The AI path is the real workhorse — this exists so the app remains
    usable without an API key, not as a parser substitute.
    """
    return SupportNotesData(
        # product / language / year / month set by the caller from subject
        header_title="",
        header_strapline="",
        subscribe_url="",
        section1=EditorialSection(),
        section2=EditorialSection(),
        upcoming_webinars=[],
        latest_release=ReleaseHighlight(),
        preheader="",
    )
