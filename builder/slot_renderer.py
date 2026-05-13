"""Render `SupportNotesData` into per-slot HTML strings.

Returns a ``dict[str, str]`` mapping each slot key to its rendered HTML.
The template's ``<div data-type="slot" data-key="X"></div>`` markers are
then replaced with the corresponding HTML by ``email_builder.render_html()``.

Design notes
------------
The HTML patterns in this module are reused verbatim (with field
substitution) from the April 2026 Tessent shipped email, which is our
known-good reference. Each dynamic-slot renderer is a small function that
takes the relevant fields from `SupportNotesData` and emits the SFMC
content-builder-flavoured HTML.

Static slots (footer, contact icon, archive footnote) are pulled in as
constants from `builder.static_slots`.

Image slots (headshots) require an SFMC CDN URL; ``slot_renderer`` does
not upload images — that's the caller's responsibility.

Placeholders
------------
When a field is missing or blank, the renderer emits an HTML comment
``<!-- TODO: <slot> -->`` so the user sees the gap in SFMC Content Builder
preview rather than getting a broken-looking email. ``has_placeholders``
returns the list of slots still containing such markers.
"""

from __future__ import annotations

import html as _html
import re
from typing import Dict, List

from builder import icon_config, language_config, static_slots
from builder.models import (
    Article,
    EditorialSection,
    ReleaseHighlight,
    Speaker,
    SupportNotesData,
    WebinarHighlight,
)

# All slot keys the SFMC template expects. If we forget one, the template
# will retain a literal `<div data-type="slot" data-key="X"></div>` in the
# output, which is harmless but visually awkward — `email_builder` warns
# about any slot in this list that we didn't render.
ALL_SLOT_KEYS: List[str] = [
    "preheader",
    "headertitle",
    "headersubscribebuttondate",
    "headerstrapline",
    "introspeel",
    "section1quote",
    "section1headshot",
    "a3d2cnhpoq",                  # speaker 1 name & title (auto-key)
    "section1editorial",
    "section1resourcenamesleftcol",
    "section1resourcenamesrightcol",
    "section2quote",
    "section2headshot",
    "section2nameandtitle",
    "section2editorial",
    "section2resourcenamesleftcol",
    "section2resourcenamesrightcol",
    "section3fullwidth",
    "section3contacticon",
    "section3contactdetails",
    "section3highlightrightcol",
    "section3resourcesrightcol",
    "section3fullwidth2",
    "footersocialmediaicons",
    "footertext",
]


_QUILL_EMPTY_P = re.compile(r'<p>\s*(?:<br\s*/?>|&nbsp;)?\s*</p>', re.IGNORECASE)
_HREF_RE = re.compile(r'href="([^"]*)"', re.IGNORECASE)
_A_TAG_RE = re.compile(r'(<a\b[^>]*>)(.*?)(</a>)', re.IGNORECASE | re.DOTALL)
_HAS_TITLE_RE = re.compile(r'\btitle\s*=', re.IGNORECASE)
_STRIP_TAGS_RE = re.compile(r'<[^>]+>')


def unescape_href_amps(html: str) -> str:
    """Decode &amp; → & inside href attribute values.

    Quill correctly encodes bare & as &amp; in HTML attributes, but SFMC's link
    engine expects raw & in URL query strings and strips links that contain &amp;.
    Call this before sending any Quill-edited HTML to SFMC.
    """
    return _HREF_RE.sub(
        lambda m: 'href="' + m.group(1).replace("&amp;", "&") + '"',
        html,
    )


def ensure_anchor_titles(html_str: str) -> str:
    """Add title="…" to every <a> tag that lacks one, using its visible link text.

    SFMC link-tracking reports use the title attribute to label each click.
    Any anchor without a title shows up as unlabelled in reports.
    """
    def _fix(m: re.Match) -> str:
        open_tag, inner_html, close_tag = m.group(1), m.group(2), m.group(3)
        if _HAS_TITLE_RE.search(open_tag):
            return m.group(0)
        text = _STRIP_TAGS_RE.sub("", inner_html).strip()
        text = _html.unescape(text)
        if not text:
            return m.group(0)  # image-only link — skip
        escaped = _html.escape(text, quote=True)
        new_open = open_tag[:-1] + f' title="{escaped}">'
        return new_open + inner_html + close_tag

    return _A_TAG_RE.sub(_fix, html_str)


def _strip_quill_cruft(html: str) -> str:
    """Remove empty <p><br></p> paragraphs and fix href encoding for SFMC."""
    if not html:
        return html
    html = _QUILL_EMPTY_P.sub("", html)
    html = unescape_href_amps(html)
    return html.strip()


def _placeholder(slot_key: str, hint: str = "") -> str:
    """Render an HTML comment placeholder for an unfilled slot."""
    note = f": {hint}" if hint else ""
    return f"<!-- TODO {slot_key}{note} -->"


def has_placeholders(rendered: Dict[str, str]) -> List[str]:
    """Return the list of slot keys whose rendered HTML still has TODOs."""
    return [k for k, v in rendered.items() if "<!-- TODO" in v]


# ---------------------------------------------------------------------------
# Wrapping helper — every slot's outer markup follows this exact pattern.
# ---------------------------------------------------------------------------

_WRAPPER_OPEN = (
    '<table cellpadding="0" cellspacing="0" class="stylingblock-content-wrapper" '
    'role="presentation" style="min-width: 100%; " width="100%"><tr>'
    '<td class="stylingblock-content-wrapper camarker-inner">'
)
_WRAPPER_CLOSE = "</td></tr></table>"


def _wrap(inner_html: str) -> str:
    return _WRAPPER_OPEN + inner_html + _WRAPPER_CLOSE


# ---------------------------------------------------------------------------
# Header slots
# ---------------------------------------------------------------------------

def render_headertitle(data: SupportNotesData) -> str:
    """e.g. ``TESSENT 지원 노트``"""
    title = data.header_title.strip()
    if not title:
        return _placeholder("headertitle", "header_title is empty")
    inner = (
        '<span style="font-size:28px;">'
        '<span style="font-family:Arial,Helvetica,sans-serif;">'
        '<span style="font-weight: 400;">'
        f"<b>{_html.escape(title)}</b>"
        "</span></span></span>"
    )
    return _wrap(inner)


def render_headersubscribebuttondate(data: SupportNotesData) -> str:
    """The "구독신청" button + the date label.

    SFMC's content-builder layout puts these as two stacked stylingblocks
    inside a single slot, so we emit them concatenated.
    """
    cfg = language_config.get(data.language)
    date_label = _localised_date_label(data, cfg)
    date_block = (
        '<table cellpadding="0" cellspacing="0" class="stylingblock-content-wrapper" '
        'role="presentation" style="min-width: 100%; " width="100%"><tr>'
        '<td class="stylingblock-content-wrapper camarker-inner">'
        '<div style="text-align: right;margin:5px 2px;white-space: nowrap;">'
        '<span style="font-size:13px;">'
        '<span style="font-family:Arial,Helvetica,sans-serif;">'
        '<span style="font-weight: 400;">'
        f"<b>{_html.escape(date_label)}</b>"
        "</span></span></span></div></td></tr></table>"
    )
    return static_slots.get_subscribe_button(data.language, data.subscribe_url, data.subscribe_button_text) + date_block


def render_headerstrapline(data: SupportNotesData) -> str:
    """One-line product tagline under the header."""
    strap = data.header_strapline.strip()
    if not strap:
        return _placeholder("headerstrapline", "header_strapline is empty")
    inner = (
        '<span style="font-family:Arial,Helvetica,sans-serif;">'
        '<span style="font-size:13px;">'
        f"{_html.escape(strap)}"
        "</span></span>"
    )
    return _wrap(inner)


def render_introspeel(data: SupportNotesData) -> str:
    """Static intro speech (only present in some product variants).

    For Tessent and Functional Verification this slot is left empty in the
    shipped emails — the strapline carries the equivalent welcome copy.
    """
    return ""  # intentionally blank — no TODO marker needed


# ---------------------------------------------------------------------------
# Section 1 / 2 — editorial content
# ---------------------------------------------------------------------------

def render_quote(slot_key: str, section: EditorialSection, lang_attr: str) -> str:
    if not section.quote.strip():
        return _placeholder(slot_key, "section quote is empty")
    inner = (
        f'<span lang="{lang_attr}" style="font-family:Arial,Helvetica,sans-serif;">'
        '<span style="font-size:16px;">'
        '<span style="font-weight: 400;">'
        f"<b>{_html.escape(section.quote.strip())}</b>"
        "</span></span></span>"
    )
    return _wrap(inner)


def render_headshot(slot_key: str, speaker: Speaker) -> str:
    """120×120 headshot image. The `speaker.photo_url` must be a CDN URL
    pointing to an already-uploaded image."""
    if not speaker.photo_url:
        return _placeholder(slot_key, f"headshot for {speaker.name!r} not uploaded")
    safe_alt = _html.escape(speaker.name or "")
    # Wrap in a centering table so the image aligns centre within the 160px column.
    inner = (
        '<table width="100%" cellspacing="0" cellpadding="0" role="presentation">'
        '<tr><td align="center">'
        f'<img src="{_html.escape(speaker.photo_url, quote=True)}" alt="{safe_alt}" '
        'height="120" width="120" '
        'style="display: block; padding: 0px; text-align: center; '
        'height: 120px; width: 120px; border: 0px;"/>'
        '</td></tr></table>'
    )
    return _wrap(inner)


def render_nameandtitle(slot_key: str, speaker: Speaker, lang_attr: str) -> str:
    if not speaker.name.strip():
        return _placeholder(slot_key, "speaker name is empty")
    title = speaker.title or "Applications Engineer"
    inner = (
        '<div style="text-align: center;">\n<br/>\n'
        '<span style="font-size:13px;">'
        f'<span lang="{lang_attr}" style="font-family:Arial,Helvetica,sans-serif;">'
        f"<b>{_html.escape(speaker.name.strip())}</b><br/>\n"
        f"\t{_html.escape(title)}"
        "</span></span></div>"
    )
    return _wrap(inner)


def render_editorial(slot_key: str, section: EditorialSection, lang_attr: str) -> str:
    """Editorial paragraph. Inline tags from `editorial_html` are preserved."""
    body = section.editorial_html.strip()
    if not body:
        return _placeholder(slot_key, "editorial body is empty")
    # If editorial_html already contains inline tags, trust them; otherwise
    # html-escape plain text. Heuristic: presence of '<' indicates HTML.
    safe_body = body if "<" in body else _html.escape(body)
    inner = f'<span lang="{lang_attr}">{safe_body}</span>'
    return _wrap(inner)


def render_resource_with_icon(
    slot_key: str,
    icon_url: str,
    icon_height: int,
    icon_width: int,
    icon_asset_id: str,
    article_url: str,
    article_label: str,
    article_alias: str,
) -> str:
    """The shared shape used by both the leftcol KBA-link slot and the
    rightcol tag-chip slot — both have the same icon-then-link layout."""
    if not article_label.strip() or not article_url.strip():
        return _placeholder(slot_key, "resource link is incomplete")
    inner = (
        '<table border="0" cellpadding="5" cellspacing="0" style="width:100%;">\n'
        '<tr>\n'
        '<td style="text-align: center;" width="20">\n'
        '<span style="font-size:13px;">'
        '<span style="font-family:Arial,Helvetica,sans-serif;">'
        f'<img alt="" data-assetid="{icon_asset_id}" height="{icon_height}" '
        f'src="{_html.escape(icon_url, quote=True)}" '
        f'style="padding: 0px; height: {icon_height}px; width: {icon_width}px; '
        'text-align: center; border: 0px;" '
        f'width="{icon_width}"/></span></span></td><td>\n'
        '<span style="font-size:13px;">'
        '<span style="font-family:Arial,Helvetica,sans-serif;">'
        f'<a alias="{_html.escape(article_alias, quote=True)}" conversion="false" '
        f'data-linkto="https://" href="{_html.escape(article_url, quote=True)}" '
        'style="text-decoration:underline;" '
        f'title="{_html.escape(article_alias, quote=True)}">'
        f"{_html.escape(article_label)}</a>"
        '</span></span></td></tr></table>'
    )
    return _wrap(inner)


def _render_article_column(
    slot_key: str,
    articles: List[Article],
    icon_slot: str,
    icon_size: int = 20,
) -> str:
    """Render N stacked icon+link rows for one resource column.

    Each `Article` produces one row; rows are concatenated so they stack
    vertically inside the slot div.  Returns a placeholder when the list is
    empty or all entries are incomplete.
    """
    rows = []
    for art in articles:
        if not art.label.strip() or not art.url.strip():
            continue
        # Per-article icon overrides the column default when set and uploaded.
        if art.icon_name:
            icon_url = icon_config.get_url_for_icon(art.icon_name) or icon_config.get_url(icon_slot)
        else:
            icon_url = icon_config.get_url(icon_slot)
        rows.append(render_resource_with_icon(
            slot_key,
            icon_url=icon_url,
            icon_height=icon_size,
            icon_width=icon_size,
            icon_asset_id="",
            article_url=art.url,
            article_label=art.label,
            article_alias=art.label,
        ))
    if not rows:
        return _placeholder(slot_key, "no articles supplied")
    return "".join(rows)


def render_resource_left(slot_key: str, section: EditorialSection) -> str:
    """Left column — document icon + stacked article links."""
    return _render_article_column(slot_key, section.left_articles, "kba_left", icon_size=20)


def render_resource_right(slot_key: str, section: EditorialSection) -> str:
    """Right column — tag/article icon + stacked article links."""
    return _render_article_column(slot_key, section.right_articles, "kba_right", icon_size=19)


# ---------------------------------------------------------------------------
# Section 3 — webinar callout, latest release, contact info
# ---------------------------------------------------------------------------

def _render_webinar_callout(data: SupportNotesData) -> str:
    """Webinar callout HTML: "Got more questions?" header + bullet list + series link.

    Returns an empty string when there are no webinars and no series URL so
    the contact column degrades gracefully.
    """
    has_webinars = any(w.title.strip() for w in data.upcoming_webinars)
    has_series = data.webinar_series_url.strip()
    if not has_webinars and not has_series:
        return ""

    cfg = language_config.get(data.language)
    lang_attr = cfg.html_lang

    # "Still have questions?" / "Got more questions?" header.
    # Use AI-extracted text when available (EML import path); otherwise fall
    # back to the localised phrase template (PPTX import and manual entry).
    if data.webinar_header_html:
        header_html = (
            '<br/>\n'
            '<span style="font-size:13px;">'
            '<span style="font-family:Arial,Helvetica,sans-serif;">'
            f'<span lang="{lang_attr}">'
            + data.webinar_header_html +
            '</span></span></span>'
        )
    else:
        # Use the extracted webinar_series_url when available so the inline
        # link points to the right destination; fall back to the EN/global
        # webinar KB article if nothing was extracted.
        _webinar_href = (
            data.webinar_series_url.strip()
            if data.webinar_series_url.strip()
            else "http://support.sw.siemens.com/en-US/knowledge-base/MG617021"
        )
        _pre_link = _localised_phrase("pre_link", data.language)
        header_html = (
            '<br/>\n'
            '<span style="font-size:13px;">'
            '<span style="font-family:Arial,Helvetica,sans-serif;">'
            f'<span lang="{lang_attr}">'
            f'<b>{_localised_phrase("further_questions", data.language)}</b>'
            f'{_pre_link}'
            '<a alias="Register for upcoming webinars" conversion="false" '
            'data-linkto="http://" '
            f'href="{_webinar_href}" '
            'style="color:#000000;text-decoration:underline;" '
            'title="Register for upcoming webinars">'
            f'{_localised_phrase("upcoming_webinar", data.language)}</a>'
            f'{_localised_phrase("ask_experts", data.language)}'
            '</span></span></span>'
        )

    # Bullet list — one <li> per webinar entry
    bullets_html = ""
    if has_webinars:
        items = []
        for web in data.upcoming_webinars:
            if not web.title.strip():
                continue
            date_part = (
                _html.escape(web.date_label.strip()) + " - "
                if web.date_label.strip() else ""
            )
            href = _html.escape(web.url.strip(), quote=True) if web.url.strip() else "#"
            items.append(
                "<li>\n"
                '<span style="font-family:Arial,Helvetica,sans-serif;">'
                '<span style="font-size:13px;">'
                f"{date_part}"
                f'<a href="{href}" style="color:#000000;text-decoration:underline;">'
                f"{_html.escape(web.title.strip())}</a>"
                "</span></span></li>\n"
            )
        if items:
            bullets_html = '<ul type="disc">\n' + "".join(items) + "</ul>"

    # Webinar series link — only rendered when the webinar URL is NOT already
    # embedded inline in the header sentence (i.e. pre_link is empty).
    # For English the URL is folded into "Still have questions? … upcoming live
    # webinars." so a duplicate series block would create a double link.
    series_html = ""
    _has_inline_link = bool(_localised_phrase("pre_link", data.language)) if not data.webinar_header_html else False
    if has_series and not _has_inline_link:
        series_html = (
            '<span style="font-size:13px;">'
            '<span style="font-family:Arial,Helvetica,sans-serif;">'
            f'<a alias="Webinar series" conversion="false" data-linkto="https://" '
            f'href="{_html.escape(data.webinar_series_url.strip(), quote=True)}" '
            'style="color:#000000;text-decoration:underline;" '
            f'title="Webinar series">'
            f"{_localised_phrase('webinar_series', data.language, product=data.product)}</a>"
            f"{_localised_phrase('check_it_out', data.language)}"
            "</span></span><br/><br/>"
        )

    # Optional promo block (any product)
    promo_html = data.promo_block_html.strip() or ""

    inner = bullets_html + promo_html + series_html
    return header_html + _wrap(inner)


def contact_details_default(data: SupportNotesData) -> str:
    """Full default content for the contact-details editable field.

    Combines the static contact body (support-centre text + Expert Series logo)
    with the dynamic webinar callout ("Got more questions?" + bullets + series).
    Used to seed the editable field on first load and as the render fallback
    when ``data.contact_body_html`` is empty.
    """
    return static_slots.get_contact_body(data.language) + _render_webinar_callout(data)


def render_section3_contactdetails(data: SupportNotesData) -> str:
    """Left column: uses ``data.contact_body_html`` as-is when set.

    The editable field in the UI is seeded with ``contact_details_default()``
    so it contains the full expected content (contact text + logo + webinar
    callout).  Whatever the user saves in that field is what gets rendered —
    no content is appended here.
    """
    cleaned = _strip_quill_cruft(data.contact_body_html)
    return cleaned if cleaned else contact_details_default(data)


def render_section3_highlight(data: SupportNotesData) -> str:
    """Bordered right box: latest-release download links."""
    components = data.latest_release.components
    if not components:
        return _placeholder("section3highlightrightcol", "no release components")

    rows = []
    for c in components:
        if not c.label.strip():
            continue
        if c.url.strip():
            link = (
                f'<a alias="{_html.escape(c.label, quote=True)}" conversion="false" '
                f'data-linkto="https://" href="{_html.escape(c.url, quote=True)}" '
                'style="color:#009999;text-decoration:underline;" '
                f'title="{_html.escape(c.label, quote=True)}">'
                f"{_html.escape(c.label)}</a>"
            )
        else:
            link = _html.escape(c.label)
        rows.append(link)

    latest_label = _localised_phrase("latest_release", data.language)
    body_html = (
        '<span style="font-size:13px;">'
        '<span style="font-family:Arial,Helvetica,sans-serif;">'
        '<span style="line-height:1.5em;">'
        f'<span style="color:#000000;"><b>{_html.escape(latest_label)}</b></span><br/><br/>'
        + "<br/>".join(rows)
        + "</span></span></span>"
    )
    inner = (
        '<table cellpadding="0" cellspacing="0" class="stylingblock-content-wrapper" '
        'role="presentation" style="background-color: transparent; min-width: 100%; " '
        'width="100%"><tr>'
        '<td class="stylingblock-content-wrapper camarker-inner" style="padding: 6px 3px;">'
        f"{body_html}"
        "</td></tr></table>"
    )
    return _wrap(inner)


def render_section3_resources(data: SupportNotesData) -> str:
    """No longer rendered into the template — returns empty string."""
    return ""


# ---------------------------------------------------------------------------
# Localised phrases — small lookup table for the few words that appear in
# every email at fixed positions but in the language of the audience.
# ---------------------------------------------------------------------------

_PHRASES = {
    "ko": {
        "further_questions":  "더 궁금한 점이 있으신가요? ",
        "pre_link":           "",
        "upcoming_webinar":   "다가오는 라이브 웨비나",
        "ask_experts":        "에서 전문가들에게 궁금한 것들을 질문해 보세요.",
        "download":           "다운로드",
        "latest_release":     "최신 릴리스",
        "webinar_series":     "{product} 한국어 웨비나 (Webinar) 시리즈",
        "check_it_out":       "를 확인해 보세요.",
        "month_format":       "{year}년 {month}월",
    },
    "en": {
        "further_questions":  "Still have questions? ",
        # pre_link text appears between the bold intro and the hyperlink.
        # For English the sentence reads: "Still have questions?  Quiz our
        # experts at our [upcoming live webinars]." — no separate series block.
        "pre_link":           " Quiz our experts at our ",
        "upcoming_webinar":   "upcoming live webinars",
        "ask_experts":        ".",
        "download":           "Download",
        "latest_release":     "Latest release",
        "webinar_series":     "{product} webinar series",
        "check_it_out":       " — check it out.",
        "month_format":       "{month_name} {year}",
    },
    "ja": {
        "further_questions":  "他にご質問はありますか? ",
        "pre_link":           "",
        "upcoming_webinar":   "ライブウェビナー",
        "ask_experts":        "で専門家に質問してみましょう。",
        "download":           "ダウンロード",
        "latest_release":     "最新リリース",
        "webinar_series":     "{product} 日本語ウェビナーシリーズ",
        "check_it_out":       "をご確認ください。",
        "month_format":       "{year}年{month}月",
    },
    "zh-CN": {
        "further_questions":  "还有疑问吗? ",
        "pre_link":           "",
        "upcoming_webinar":   "即将举办的网络研讨会",
        "ask_experts":        " — 向专家提问您关心的问题。",
        "download":           "下载",
        "latest_release":     "最新版本",
        "webinar_series":     "{product} 中文网络研讨会系列",
        "check_it_out":       " — 立即查看。",
        "month_format":       "{year}年{month}月",
    },
    "zh-TW": {
        "further_questions":  "還有其他問題嗎? ",
        "pre_link":           "",
        "upcoming_webinar":   "即將舉行的網路研討會",
        "ask_experts":        " — 向專家提出您想了解的問題。",
        "download":           "下載",
        "latest_release":     "最新版本",
        "webinar_series":     "{product} 中文網路研討會系列",
        "check_it_out":       " — 立即查看。",
        "month_format":       "{year}年{month}月",
    },
}

_EN_MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _localised_phrase(key: str, language: str, **kwargs) -> str:
    template = _PHRASES.get(language, _PHRASES["ko"]).get(key, "")
    if "{product}" in template and "product" not in kwargs:
        kwargs["product"] = ""
    return template.format(**kwargs) if "{" in template else template


def _localised_date_label(data: SupportNotesData, cfg) -> str:
    if not (data.year and data.month):
        return ""
    if data.language == "en":
        month_name = _EN_MONTH_NAMES[data.month] if 1 <= data.month <= 12 else ""
        return f"{month_name} {data.year}"
    return _PHRASES.get(data.language, _PHRASES["ko"])["month_format"].format(
        year=data.year, month=data.month
    )


# ---------------------------------------------------------------------------
# Top-level renderer
# ---------------------------------------------------------------------------

def render_slots(data: SupportNotesData) -> Dict[str, str]:
    """Produce the full mapping of slot_key → HTML for the SupportNotesData."""
    cfg = language_config.get(data.language)
    lang_attr = cfg.html_lang

    out: Dict[str, str] = {}

    # Preheader — set on SFMC asset metadata, not rendered into HTML body.
    # We still emit a value here for `email_builder` to consume.
    out["preheader"] = data.preheader.strip() or _placeholder("preheader")

    # Header
    out["headertitle"] = render_headertitle(data)
    out["headersubscribebuttondate"] = render_headersubscribebuttondate(data)
    out["headerstrapline"] = render_headerstrapline(data)
    out["introspeel"] = render_introspeel(data)

    # Section 1
    out["section1quote"] = render_quote("section1quote", data.section1, lang_attr)
    out["section1headshot"] = render_headshot("section1headshot", data.section1.speaker)
    out["a3d2cnhpoq"] = render_nameandtitle("a3d2cnhpoq", data.section1.speaker, lang_attr)
    out["section1editorial"] = render_editorial("section1editorial", data.section1, lang_attr)
    out["section1resourcenamesleftcol"] = render_resource_left(
        "section1resourcenamesleftcol", data.section1
    )
    out["section1resourcenamesrightcol"] = render_resource_right(
        "section1resourcenamesrightcol", data.section1
    )

    # Section 2
    out["section2quote"] = render_quote("section2quote", data.section2, lang_attr)
    out["section2headshot"] = render_headshot("section2headshot", data.section2.speaker)
    out["section2nameandtitle"] = render_nameandtitle(
        "section2nameandtitle", data.section2.speaker, lang_attr
    )
    out["section2editorial"] = render_editorial("section2editorial", data.section2, lang_attr)
    out["section2resourcenamesleftcol"] = render_resource_left(
        "section2resourcenamesleftcol", data.section2
    )
    out["section2resourcenamesrightcol"] = render_resource_right(
        "section2resourcenamesrightcol", data.section2
    )

    # Section 3
    out["section3fullwidth"] = static_slots.EMPTY_SLOT_HTML
    out["section3contacticon"] = static_slots.section3_contacticon_html()
    out["section3contactdetails"] = render_section3_contactdetails(data)
    out["section3highlightrightcol"] = render_section3_highlight(data)
    out["section3resourcesrightcol"] = render_section3_resources(data)
    out["section3fullwidth2"] = (
        _strip_quill_cruft(data.footnote_html) or static_slots.get_footnote(data.language)
    )

    # Footer
    out["footersocialmediaicons"] = static_slots.EMPTY_SLOT_HTML
    out["footertext"] = _strip_quill_cruft(data.footer_html) or static_slots.get_footer(data.language)

    # Sanity: every documented slot must be in the output.
    missing = [k for k in ALL_SLOT_KEYS if k not in out]
    if missing:
        raise RuntimeError(f"render_slots forgot to render: {missing}")

    # Ensure every <a> has title= for SFMC link-tracking reports.
    out = {k: ensure_anchor_titles(v) for k, v in out.items()}

    return out
