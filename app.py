"""Streamlit UI: upload a Support Notes request `.eml`, review the AI-extracted
slot data, upload speaker headshots, and create the rendered email asset in
Salesforce Marketing Cloud Content Builder.

Mirrors the architecture of the Expert Series Webinar Invite Builder
(`https://github.com/rosdevries/expert-series-webinar-invite-builder/blob/master/app.py`).

Differences from the webinar app:
  * Source = uploaded `.eml` instead of a URL.
  * A language picker drives the per-language template + folder lookup.
  * Headshots are auto-composited onto the brand-green canvas before upload.
"""

from __future__ import annotations

import datetime
import io
import os
import re
import traceback
from pathlib import Path

from PIL import Image

import streamlit as st
from dotenv import load_dotenv
from streamlit_quill import st_quill

# ---------------------------------------------------------------------------
# Bootstrap — same secrets-bridging pattern the webinar app uses, since
# Streamlit Cloud secrets aren't always reflected into os.environ.
# ---------------------------------------------------------------------------

load_dotenv()

_SECRET_KEYS = [
    "APP_PASSWORD",
    "MC_CLIENT_ID", "MC_CLIENT_SECRET", "MC_AUTH_BASE_URI", "MC_REST_BASE_URI",
    "MC_ACCOUNT_ID", "MC_TEMPLATE_FOLDER_ID", "MC_IMAGES_FOLDER_ID",
    "MC_EMAIL_FOLDER_ID_KO", "MC_EMAIL_FOLDER_ID_EN", "MC_EMAIL_FOLDER_ID_JP",
    "MC_EMAIL_FOLDER_ID_ZH_CN", "MC_EMAIL_FOLDER_ID_ZH_TW",
    "MC_TEMPLATE_ID",
    "ANTHROPIC_API_KEY",
]
for _k in _SECRET_KEYS:
    try:
        v = st.secrets[_k]
        if v:
            os.environ[_k] = str(v)
    except Exception:
        pass

# Imports must follow secrets bridging — sfmc_client / language_config read env at use time.
from builder import (  # noqa: E402
    draft_store,
    email_builder,
    eml_parser,
    headshot_compositor,
    icon_config,
    icon_library,
    language_config,
    pptx_parser,
    sfmc_client,
    slot_renderer,
    static_slots,
)
from builder.models import (  # noqa: E402
    Article,
    EditorialSection,
    ReleaseComponent,
    ReleaseHighlight,
    Speaker,
    SupportNotesData,
)

SFMC_CONTENT_BUILDER_URL = (
    "https://mc.s7.exacttarget.com/cloud/#app/Email/C12/Default.aspx"
    "?entityType=none&entityID=0&ks=ks%23Content"
)

# ---------------------------------------------------------------------------
# Page setup + password gate
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Support Notes → SFMC", page_icon="📰", layout="wide")

try:
    PW = st.secrets["APP_PASSWORD"]
except Exception:
    PW = os.getenv("APP_PASSWORD", "changeme")

if not st.session_state.get("authed"):
    with st.form("login"):
        pw = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in"):
            if pw == PW:
                st.session_state.authed = True
                st.rerun()
            else:
                st.error("Incorrect password")
    st.stop()

st.title("📰 Support Notes → SFMC")
st.caption(
    "Upload a Support Notes request `.eml` or `.pptx`, review the extracted content, "
    "upload speaker headshots, and create the email asset in SFMC."
)


# ---------------------------------------------------------------------------
# Session-state helpers
# ---------------------------------------------------------------------------

def _ensure_state(key, default):
    if key not in st.session_state:
        st.session_state[key] = default


_ensure_state("data", None)             # SupportNotesData under edit
_ensure_state("eml_attachments", [])    # List[EmlAttachment] from the parsed .eml
_ensure_state("photo_urls", {})         # speaker_name -> SFMC CDN URL
_ensure_state("upload_gen", 0)          # bumps on each new .eml upload (to reset widget keys)
_ensure_state("last_create_result", None)


_TABLE_TAGS_RE = re.compile(
    r'</?(?:table|tbody|thead|tfoot|tr|td|th)\b[^>]*>',
    re.IGNORECASE,
)


def _quill_seed(html: str) -> str:
    """Strip HTML table structural elements before passing to Quill.

    Quill's sanitiser discards <table>/<tr>/<td> elements and silently drops
    their content too, so the webinar bullet list (which lives inside the
    _wrap() table shell) never appears in the visual editor.  Removing the
    structural tags first leaves only the inner content — spans, <ul>/<li>,
    <img>, <hr> — which Quill renders and lets the user edit normally.
    """
    return _TABLE_TAGS_RE.sub('', html)


def _images_folder_id() -> int:
    raw = os.environ.get("MC_IMAGES_FOLDER_ID", "").strip()
    if not raw:
        raise RuntimeError("MC_IMAGES_FOLDER_ID is not set")
    return int(raw)


def _short_name(s: str, n: int = 60) -> str:
    s = s.strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _rich_editor(
    initial: str,
    key: str,
    placeholder: str = "",
    dark_preview: str = "",
) -> str:
    """Quill WYSIWYG editor with HTML source toggle, persists content across reruns.

    Uses a radio to switch between Visual (Quill) and HTML (textarea) modes.
    Only one widget renders at a time so they can't overwrite each other's state.
    When switching to HTML mode the textarea is re-seeded from the current stored
    value so it always reflects the latest Visual edits (and vice-versa).

    ``dark_preview``: when set to a CSS background colour (e.g. ``"#000028"``),
    Visual mode renders a styled read-only iframe preview instead of the Quill editor —
    useful for fields whose final email context has a dark background (e.g. footer).
    Switch to HTML mode to edit the content.
    """
    stored = f"_re_{key}"
    mode_key = f"_re_mode_{key}"

    if stored not in st.session_state:
        st.session_state[stored] = initial
    if mode_key not in st.session_state:
        st.session_state[mode_key] = "Visual"

    prev_mode = st.session_state[mode_key]
    mode = st.radio(
        "Edit mode",
        ["Visual", "HTML"],
        key=f"{key}_mode_radio",
        horizontal=True,
        index=0 if prev_mode == "Visual" else 1,
        label_visibility="collapsed",
    )
    st.session_state[mode_key] = mode

    if mode == "Visual":
        if dark_preview:
            content = st.session_state[stored] or f'<span style="opacity:.4">{placeholder}</span>'
            preview_html = f"""<!DOCTYPE html>
<html><head><style>
  body {{
    margin: 0; padding: 12px 16px;
    background: {dark_preview};
    font-family: Arial, Helvetica, sans-serif;
    font-size: 11px; line-height: 1.6;
    color: #ffffff;
  }}
  a, a:visited {{ color: #ffffff; text-decoration: underline; }}
  p {{ margin: 0 0 6px 0; }}
</style></head>
<body>{content}</body></html>"""
            st.iframe(preview_html, height=160)
            st.caption("Read-only preview — switch to **HTML** to edit.")
        else:
            result = st_quill(
                placeholder=placeholder,
                html=True,
                value=st.session_state[stored],
                key=f"{key}_quill",
            )
            if result is not None:
                # Strip the empty-paragraph artefacts Quill inserts for blank lines.
                result = re.sub(r'<p>\s*(?:<br\s*/?>|&nbsp;)?\s*</p>', '', result, flags=re.IGNORECASE).strip()
                st.session_state[stored] = result
    else:
        ta_key = f"{key}_html_area"
        # When switching into HTML mode, drop stale textarea state so it re-seeds
        # from the current stored value rather than whatever it held last time.
        if prev_mode != "HTML" and ta_key in st.session_state:
            del st.session_state[ta_key]
        # Seed the textarea session state on first entry into HTML mode.
        # We set st.session_state[ta_key] directly rather than using value= to
        # avoid Streamlit resetting the widget (and losing edits) on every rerun.
        if ta_key not in st.session_state:
            _HREF_RE_DISPLAY = re.compile(r'href="([^"]*)"', re.IGNORECASE)
            st.session_state[ta_key] = _HREF_RE_DISPLAY.sub(
                lambda m: 'href="' + m.group(1).replace("&amp;", "&") + '"',
                st.session_state[stored],
            )
        html_val = st.text_area(
            "HTML source",
            key=ta_key,
            height=200,
            label_visibility="collapsed",
        )
        st.session_state[stored] = html_val

    return st.session_state[stored]


# ---------------------------------------------------------------------------
# Step 1 — Language picker + .eml upload
# ---------------------------------------------------------------------------

st.subheader("1. Upload a request")

col_lang, col_file = st.columns([1, 3])
with col_lang:
    # Build {label: code} dict so the dropdown shows the human-readable name.
    lang_options = dict(sorted(
        {cfg.label: code for code, cfg in language_config.LANGUAGES.items()}.items()
    ))
    chosen_label = st.selectbox(
        "Language",
        list(lang_options.keys()),
        key="lang_picker",
    )
    chosen_lang = lang_options[chosen_label]

with col_file:
    eml_file = st.file_uploader(
        "Drop the request file here (.eml or .pptx)",
        type=["eml", "pptx"],
        key=f"eml_uploader_{st.session_state.upload_gen}",
    )

col_parse, col_fresh, col_dbg = st.columns([3, 2, 1])
with col_parse:
    parse_btn = st.button("📥 Parse and extract", type="primary", disabled=eml_file is None)
with col_fresh:
    fresh_btn = st.button("✏️ Start from scratch", help="Open a blank form to build an email manually")
with col_dbg:
    debug_mode = st.checkbox("Show debug info", value=False)

if parse_btn and eml_file is not None:
    _is_pptx = eml_file.name.lower().endswith(".pptx")
    _spinner_msg = "Parsing PPTX…" if _is_pptx else "Parsing .eml and extracting content with Claude…"
    with st.spinner(_spinner_msg):
        try:
            raw = eml_file.read()
            if _is_pptx:
                data, _pptx_images = pptx_parser.parse(raw)
                data.language = chosen_lang
                ai_error = None
                _attachments = _pptx_images
            else:
                parsed = eml_parser.parse(raw)
                data, ai_error = email_builder.parse_only(io.BytesIO(raw), language=chosen_lang)
                _attachments = parsed.attachments
            if ai_error:
                st.warning(
                    f"⚠️ AI extraction failed — form fields will be empty. "
                    f"Fill them in manually and continue.\n\n{ai_error}"
                )

            # Restore saved draft if one exists for this product+language+year+month.
            # Keep a copy of the AI-extracted .eml fields so we can re-apply them
            # when the draft has empty values — drafts may have these cleared (e.g.
            # to remove stale SFMC tracking URLs) but the AI always re-extracts them.
            ai_upcoming_webinars = data.upcoming_webinars
            ai_webinar_header_html = data.webinar_header_html
            ai_webinar_series_url = data.webinar_series_url
            ai_footnote_html = data.footnote_html

            saved = draft_store.load(data)
            if saved is not None:
                data = saved
                # Re-apply fresh AI values for fields that are always sourced from
                # the .eml and should not be permanently blanked by draft clearing.
                if ai_upcoming_webinars and not data.upcoming_webinars:
                    # Webinars were cleared from the draft (to remove stale SFMC
                    # tracking) but the AI has fresh ones.  Re-apply all webinar
                    # data and clear contact_body_html so the contact field
                    # re-seeds from contact_details_default(), which now includes
                    # the fresh webinar callout.  Always take the AI webinar_header
                    # since it's fresher than any stale draft value.
                    data.upcoming_webinars = ai_upcoming_webinars
                    data.webinar_header_html = ai_webinar_header_html
                    if not data.webinar_series_url:
                        data.webinar_series_url = ai_webinar_series_url
                    data.contact_body_html = ""
                else:
                    if not data.webinar_header_html and ai_webinar_header_html:
                        data.webinar_header_html = ai_webinar_header_html
                    if not data.webinar_series_url and ai_webinar_series_url:
                        data.webinar_series_url = ai_webinar_series_url
                if not data.footnote_html:
                    data.footnote_html = ai_footnote_html
                st.session_state._draft_restored = True
            else:
                st.session_state._draft_restored = False

            st.session_state.data = data
            st.session_state.eml_attachments = _attachments
            st.session_state.photo_urls = {}
            st.session_state.upload_gen += 1
            st.session_state.last_create_result = None

            # Seed photo_urls from draft (so photos reappear without re-uploading)
            for spk in (data.section1.speaker, data.section2.speaker):
                if spk.name and spk.photo_url:
                    st.session_state.photo_urls[spk.name] = spk.photo_url

            # Look up existing speaker headshots in SFMC images folder
            try:
                images_folder = _images_folder_id()
                for spk in (data.section1.speaker, data.section2.speaker):
                    if spk.name and not spk.photo_url:
                        existing = sfmc_client.find_speaker_image(spk.name, images_folder)
                        if existing:
                            spk.photo_url = existing
                            st.session_state.photo_urls[spk.name] = existing
            except Exception as exc:
                if debug_mode:
                    st.caption(f"(Skipped existing-photo lookup: {exc})")
        except Exception as exc:
            st.error(f"Parse failed: {exc}")
            if debug_mode:
                st.code(traceback.format_exc())

if fresh_btn:
    _today = datetime.date.today()
    _blank = SupportNotesData(language=chosen_lang, year=_today.year, month=_today.month)
    st.session_state.data = _blank
    st.session_state.eml_attachments = []
    st.session_state.photo_urls = {}
    st.session_state.upload_gen += 1
    st.session_state.last_create_result = None
    st.session_state._draft_restored = False


# ---------------------------------------------------------------------------
# Step 2-onwards: only show if we have parsed data
# ---------------------------------------------------------------------------

data: SupportNotesData | None = st.session_state.get("data")
if data is None:
    st.info("Upload a request `.eml` above and click **Parse and extract**, or click **Start from scratch** to build manually.")
    st.stop()

st.divider()
st.subheader("2. Review and edit")

if st.session_state.get("_draft_restored"):
    st.info(
        f"✏️ **Saved edits restored** — your previous corrections for "
        f"**{draft_store.key_display(data)}** have been reapplied automatically. "
        f"Delete the draft below if you'd rather start from fresh AI extraction."
    )

# ---- Header / metadata ---------------------------------------------------
with st.container(border=True):
    st.markdown("**Metadata**")
    col_a, col_b, col_c, col_d = st.columns([2, 1, 1, 2])
    with col_a:
        data.product = st.text_input("Product", data.product, key=f"product_{st.session_state.upload_gen}")
    with col_b:
        data.year = st.number_input(
            "Year", value=data.year or 2026, min_value=2020, max_value=2099, step=1,
            key=f"year_{st.session_state.upload_gen}",
        )
    with col_c:
        data.month = st.number_input(
            "Month", value=data.month or 1, min_value=1, max_value=12, step=1,
            key=f"month_{st.session_state.upload_gen}",
        )
    with col_d:
        st.text_input(
            "Language",
            value=f"{language_config.get(data.language).label} ({language_config.get(data.language).html_lang})",
            disabled=True,
        )

    data.header_title = st.text_input(
        "Header title",
        data.header_title,
        help="e.g. 'TESSENT 지원 노트' — appears at the very top of the email",
        key=f"hdr_title_{st.session_state.upload_gen}",
    )
    data.header_strapline = st.text_area(
        "Header strapline",
        data.header_strapline,
        help="One-line product tagline immediately under the header",
        height=70,
        key=f"hdr_strap_{st.session_state.upload_gen}",
    )
    _sub_col1, _sub_col2 = st.columns([1, 2])
    with _sub_col1:
        data.subscribe_button_text = st.text_input(
            "Subscribe button text",
            data.subscribe_button_text,
            placeholder="Leave blank to use language default",
            help="Overrides the language-default label (e.g. '구독신청', 'Subscribe') when set",
            key=f"sub_text_{st.session_state.upload_gen}",
        )
    with _sub_col2:
        data.subscribe_url = st.text_input(
            "Subscribe button URL",
            data.subscribe_url,
            placeholder="Leave blank to use language default",
            help="Overrides the default account.sw.siemens.com profile URL when set",
            key=f"sub_url_{st.session_state.upload_gen}",
        )
    data.preheader = st.text_input(
        "Preheader (≤ 85 chars recommended)",
        data.preheader,
        key=f"preheader_{st.session_state.upload_gen}",
    )


# ---- Per-article icon picker ---------------------------------------------

# Bundled icons offered in the per-article picker (in display order).
_ARTICLE_ICON_OPTIONS = [
    ("kba",           "KBA"),
    ("docs",          "Docs"),
    ("download",      "↓"),
    ("youtube",       "YT"),
    ("video",         "▶"),
    ("expert-series", "ES"),
    ("support-kit",   "Kit"),
]


def _article_icon_picker(art: Article, key: str) -> None:
    """Render a compact inline icon picker. Mutates art.icon_name in place.

    Shows icon thumbnails + short-label buttons in a tight row.  Clicking an
    icon uploads it to SFMC on first use (cached in icon_config); subsequent
    selects are instant.  The '↩' button resets to the column default.
    """
    n = len(_ARTICLE_ICON_OPTIONS)
    cols = st.columns([1] * (n + 1) + [999])   # icons + reset + spacer

    with cols[0]:
        is_default = not art.icon_name
        if st.button(
            "✓" if is_default else "↩",
            key=f"{key}_default",
            help="Use column default icon",
            type="primary" if is_default else "secondary",
        ):
            art.icon_name = ""
            st.rerun()

    for j, (iname, short) in enumerate(_ARTICLE_ICON_OPTIONS):
        with cols[j + 1]:
            try:
                st.image(icon_library.render_png(iname, size=20), width=20)
            except Exception:
                pass
            is_sel = art.icon_name == iname
            if st.button(
                "✓" if is_sel else short,
                key=f"{key}_{iname}",
                help=icon_library.label(iname),
                type="primary" if is_sel else "secondary",
            ):
                if not icon_config.get_url_for_icon(iname):
                    with st.spinner(f"Uploading {icon_library.label(iname)} icon…"):
                        try:
                            _png = icon_library.render_png(iname, size=40)
                            _cdn = sfmc_client.replace_image_bytes(
                                _png,
                                speaker_name=f"icon-article-{iname}",
                                folder_id=_images_folder_id(),
                                source_filename=f"{iname}.png",
                            )
                            icon_config.set_url_for_icon(iname, _cdn)
                        except Exception as _exc:
                            st.error(f"Icon upload failed: {_exc}")
                art.icon_name = iname
                st.rerun()


# ---- Editorial section renderer -----------------------------------------

def _render_editorial_form(label: str, section: EditorialSection, idx: int) -> EditorialSection:
    """Render the form for one editorial section. Returns the (mutated) section."""
    gen = st.session_state.upload_gen
    with st.container(border=True):
        st.markdown(f"**{label}**")

        section.quote = st.text_area(
            "Question headline",
            section.quote,
            height=70,
            key=f"sec{idx}_quote_{gen}",
        )

        col_info, col_photo = st.columns([3, 1])
        with col_info:
            section.speaker.name = st.text_input(
                "Speaker name",
                section.speaker.name,
                key=f"sec{idx}_spk_name_{gen}",
            )
            section.speaker.title = st.text_input(
                "Speaker title",
                section.speaker.title or "Applications Engineer",
                key=f"sec{idx}_spk_title_{gen}",
            )
        with col_photo:
            st.caption("**Photo**")
            existing = section.speaker.photo_url
            has_photo = bool(existing) and "<!--" not in existing
            if has_photo:
                try:
                    st.image(existing, width=100)
                except Exception:
                    st.caption("📎 Photo on file")
            else:
                st.markdown(
                    '<div style="width:100px;height:100px;background:#d8d8d8;'
                    'border-radius:4px;border:1px dashed #999;"></div>',
                    unsafe_allow_html=True,
                )

            # Quick-select from headshots embedded in the uploaded PPTX.
            _pptx_imgs = [
                a for a in st.session_state.get("eml_attachments", [])
                if a.content_type.startswith("image/")
            ]
            if _pptx_imgs:
                st.caption("From PPTX:")
                for _pi, _pa in enumerate(_pptx_imgs):
                    try:
                        st.image(_pa.bytes, width=55)
                    except Exception:
                        st.caption(_pa.filename)
                    if st.button(
                        "Use",
                        key=f"sec{idx}_pptx_{gen}_{_pi}",
                        help=f"Composite and upload {_pa.filename}",
                    ):
                        if not section.speaker.name.strip():
                            st.error("Enter the speaker name first.")
                        else:
                            with st.spinner("Processing and uploading to SFMC…"):
                                try:
                                    _comp = headshot_compositor.composite_headshot(_pa.bytes)
                                    _cdn = sfmc_client.replace_image_bytes(
                                        _comp.png_bytes,
                                        section.speaker.name,
                                        _images_folder_id(),
                                        f"{section.speaker.name}.png",
                                    )
                                    section.speaker.photo_url = _cdn
                                    st.session_state.photo_urls[section.speaker.name] = _cdn
                                    st.rerun()
                                except Exception as _exc:
                                    st.error(f"Upload failed: {_exc}")

            uploaded = st.file_uploader(
                "Upload",
                type=["jpg", "jpeg", "png", "gif", "webp"],
                key=f"sec{idx}_photo_{gen}",
                label_visibility="collapsed",
            )
            track_key = f"_photo_track_{gen}_{idx}"
            if uploaded is not None:
                tracked = st.session_state.get(track_key, {})
                is_new = (
                    tracked.get("filename") != uploaded.name
                    or tracked.get("size") != uploaded.size
                )
                if is_new:
                    if not section.speaker.name.strip():
                        st.error("Enter the speaker name before uploading a photo.")
                    else:
                        with st.spinner("Processing headshot and uploading to SFMC…"):
                            try:
                                composited = headshot_compositor.composite_headshot(uploaded.read())
                                cdn_url = sfmc_client.replace_image_bytes(
                                    composited.png_bytes,
                                    section.speaker.name,
                                    _images_folder_id(),
                                    f"{section.speaker.name}.png",
                                )
                                section.speaker.photo_url = cdn_url
                                st.session_state.photo_urls[section.speaker.name] = cdn_url
                                st.session_state[track_key] = {
                                    "filename": uploaded.name,
                                    "size": uploaded.size,
                                }
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Upload failed: {exc}")

        section.editorial_html = st.text_area(
            "Editorial body (HTML or plain text)",
            section.editorial_html,
            height=140,
            key=f"sec{idx}_body_{gen}",
            help="Inline tags like <strong>/<em>/<a>/<br> are preserved.",
        )

        # Left column articles
        st.markdown("*Left column articles*")
        if not section.left_articles:
            section.left_articles = [Article()]
        for i, art in enumerate(section.left_articles):
            col_lbl, col_url, col_x = st.columns([2, 3, 1])
            with col_lbl:
                art.label = st.text_input(
                    f"Article {i + 1} label",
                    art.label,
                    key=f"sec{idx}_left_lbl_{gen}_{i}",
                    label_visibility="collapsed",
                    placeholder=f"Article {i + 1} — visible link text",
                )
            with col_url:
                art.url = st.text_input(
                    f"Article {i + 1} URL",
                    art.url,
                    key=f"sec{idx}_left_url_{gen}_{i}",
                    label_visibility="collapsed",
                    placeholder="https://support.sw.siemens.com/...",
                )
            with col_x:
                if len(section.left_articles) > 1:
                    if st.button("✕", key=f"sec{idx}_left_rm_{gen}_{i}",
                                 help="Remove this article"):
                        section.left_articles.pop(i)
                        st.rerun()
            _article_icon_picker(art, key=f"sec{idx}_left_icon_{gen}_{i}")
        if st.button("＋ Add left article", key=f"sec{idx}_left_add_{gen}"):
            section.left_articles.append(Article())
            st.rerun()

        # Right column articles
        st.markdown("*Right column articles*")
        if not section.right_articles:
            section.right_articles = [Article()]
        for i, art in enumerate(section.right_articles):
            col_lbl, col_url, col_x = st.columns([2, 3, 1])
            with col_lbl:
                art.label = st.text_input(
                    f"Article {i + 1} label",
                    art.label,
                    key=f"sec{idx}_right_lbl_{gen}_{i}",
                    label_visibility="collapsed",
                    placeholder=f"Article {i + 1} — visible link text",
                )
            with col_url:
                art.url = st.text_input(
                    f"Article {i + 1} URL",
                    art.url,
                    key=f"sec{idx}_right_url_{gen}_{i}",
                    label_visibility="collapsed",
                    placeholder="https://support.sw.siemens.com/...",
                )
            with col_x:
                if len(section.right_articles) > 1:
                    if st.button("✕", key=f"sec{idx}_right_rm_{gen}_{i}",
                                 help="Remove this article"):
                        section.right_articles.pop(i)
                        st.rerun()
            _article_icon_picker(art, key=f"sec{idx}_right_icon_{gen}_{i}")
        if st.button("＋ Add right article", key=f"sec{idx}_right_add_{gen}"):
            section.right_articles.append(Article())
            st.rerun()

    return section


data.section1 = _render_editorial_form("Section 1 — first editorial", data.section1, 1)
data.section2 = _render_editorial_form("Section 2 — second editorial", data.section2, 2)


# ---- Section 3 (right rail callouts) -------------------------------------
with st.container(border=True):
    st.markdown("**Section 3 — webinar callout & latest release**")

    _contact_label_col, _contact_reset_col = st.columns([10, 1])
    with _contact_label_col:
        st.markdown("*Support-centre contact text (left column)*")
    with _contact_reset_col:
        _contact_stored = f"_re_contact_body_{st.session_state.upload_gen}"
        if st.button("↺", key=f"reset_contact_{st.session_state.upload_gen}",
                     help="Reset to language defaults"):
            data.contact_body_html = ""
            st.session_state.data = data
            st.session_state.pop(_contact_stored, None)
            st.session_state.pop(f"{_contact_stored}_mode", None)
            st.rerun()
    data.contact_body_html = _rich_editor(
        _quill_seed(data.contact_body_html or slot_renderer.contact_details_default(data)),
        key=f"contact_body_{st.session_state.upload_gen}",
        placeholder="Support-centre contact text…",
    )

    st.markdown("*Latest release components*")
    # Render one row per existing component, with an "add row" button below.
    if not data.latest_release.components:
        data.latest_release.components = [ReleaseComponent()]
    for i, comp in enumerate(data.latest_release.components):
        col_lbl, col_url, col_x = st.columns([2, 3, 1])
        with col_lbl:
            comp.label = st.text_input(
                "Label", comp.label, key=f"rel_label_{st.session_state.upload_gen}_{i}",
                label_visibility="collapsed", placeholder="e.g. Tessent 2026.1-p1",
            )
        with col_url:
            comp.url = st.text_input(
                "URL", comp.url, key=f"rel_url_{st.session_state.upload_gen}_{i}",
                label_visibility="collapsed", placeholder="https://support.sw.siemens.com/...",
            )
        with col_x:
            if len(data.latest_release.components) > 1:
                if st.button("✕", key=f"rel_rm_{st.session_state.upload_gen}_{i}",
                             help="Remove this row"):
                    data.latest_release.components.pop(i)
                    st.rerun()
    if st.button("＋ Add release row", key=f"rel_add_{st.session_state.upload_gen}"):
        data.latest_release.components.append(ReleaseComponent())
        st.rerun()

    st.divider()
    _footnote_label_col, _footnote_reset_col = st.columns([10, 1])
    with _footnote_label_col:
        st.markdown("*Archive footnote*")
    with _footnote_reset_col:
        _footnote_stored = f"_re_footnote_{st.session_state.upload_gen}"
        if st.button("↺", key=f"reset_footnote_{st.session_state.upload_gen}",
                     help="Reset to language defaults"):
            data.footnote_html = ""
            st.session_state.data = data
            st.session_state.pop(_footnote_stored, None)
            st.session_state.pop(f"{_footnote_stored}_mode", None)
            st.rerun()
    data.footnote_html = _rich_editor(
        data.footnote_html or static_slots.get_footnote(data.language),
        key=f"footnote_{st.session_state.upload_gen}",
        placeholder="Archive footnote text…",
    )


with st.container(border=True):
    st.markdown("**Footer**")
    data.footer_html = _rich_editor(
        data.footer_html or static_slots.get_footer(data.language),
        key=f"footer_{st.session_state.upload_gen}",
        placeholder="Footer legal text…",
        dark_preview="#000028",
    )

# Auto-save draft on every render so corrections survive re-imports
draft_store.save(data)


# ---------------------------------------------------------------------------
# Step 3 — Preview + Create
# ---------------------------------------------------------------------------

st.divider()
st.subheader("3. Create the email asset")

# Live render to surface placeholders
try:
    preview = email_builder.render_html(data)
    placeholders = preview["placeholders"]
    # 'preheader' as a placeholder is just a missing preheader — surface it
    # gently rather than scarily.
    important_placeholders = [p for p in placeholders if p != "preheader"]

    if important_placeholders:
        st.warning(
            "These slots still need content before sending: "
            + ", ".join(important_placeholders)
        )
    if "preheader" in placeholders:
        st.caption("Preheader is empty — set one above for a better inbox preview.")

    with st.expander("Preview generated subject + asset name"):
        st.code(f"Subject:    {preview['subject']}")
        st.code(f"Asset name: {preview['name']}")
        st.code(f"Preheader:  {preview['preheader'] or '(none)'}")

    if debug_mode:
        with st.expander("Debug — full SupportNotesData (JSON)"):
            import json
            st.code(json.dumps(data.to_dict(), ensure_ascii=False, indent=2), language="json")

except Exception as exc:
    st.error(f"Render preview failed: {exc}")
    if debug_mode:
        st.code(traceback.format_exc())
    placeholders = []


col_create, col_sfmc = st.columns([3, 1])
with col_create:
    create_btn = st.button(
        "🚀 Create email in SFMC",
        type="primary",
        key=f"create_{st.session_state.upload_gen}",
    )
with col_sfmc:
    st.link_button("Open SFMC Content Builder →", SFMC_CONTENT_BUILDER_URL)

if create_btn:
    with st.spinner("Calling SFMC API…"):
        try:
            result = email_builder.create(data, dry_run=False)
            st.session_state.last_create_result = result
            st.success(f"Email asset created: **{result['name']}**  (ID: `{result.get('id')}`)")
            st.caption(f"Subject: _{result['subject']}_")
            if result.get("preheader"):
                st.caption(f"Preheader: _{result['preheader']}_")
            if result.get("placeholders"):
                non_pre = [p for p in result["placeholders"] if p != "preheader"]
                if non_pre:
                    st.warning(
                        "Edit these slots in SFMC before sending: " + ", ".join(non_pre)
                    )
            st.info(
                "**Reminder:** In SFMC Content Builder, open the email Properties "
                "and add the **Support Notes** campaign tag before scheduling the send."
            )
            st.link_button("View email in SFMC Content Builder →", SFMC_CONTENT_BUILDER_URL)
        except Exception as exc:
            st.error(f"SFMC create failed: {exc}")
            if debug_mode:
                st.code(traceback.format_exc())


# ---------------------------------------------------------------------------
# Footer aids
# ---------------------------------------------------------------------------

# Reset / draft management
col_restart, col_deldraft = st.columns([1, 1])
with col_restart:
    if st.button("Start over (clear session)"):
        for k in list(st.session_state.keys()):
            if k != "authed":
                del st.session_state[k]
        st.rerun()
with col_deldraft:
    if st.button(
        "🗑️ Delete saved draft",
        help=f"Remove saved edits for {draft_store.key_display(data)} so the "
             "next import uses fresh AI extraction instead.",
    ):
        draft_store.delete(data)
        # Clear overridable static fields so the next render seeds from
        # language-aware defaults rather than retaining stale content.
        data.contact_body_html = ""
        data.footnote_html = ""
        data.footer_html = ""
        st.session_state.data = data
        st.session_state._draft_restored = False
        # Increment upload_gen to force fresh widget keys (clears cached editor state).
        st.session_state.upload_gen += 1
        st.rerun()
