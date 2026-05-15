"""Parse a `.eml` Support Notes request file into a `ParsedEml` record.

The Korean (and forthcoming EN/JA/zh-CN/zh-TW) request emails follow a
consistent shape:

    Subject:  Tessent 지원 노트 - 2026년 5월
              Functional Verification 지원 노트 - 2026년 5월
              Tessent Support Notes - May 2026   (English variant)

    Body:     [editor's notes — paragraphs + tables of KBA URL pairs]
              [a single <table width="600"> that mocks the final email]
              [signature]

    Attachments:  Speaker headshots (PNG/JPG), inline preview images
                  (small image00X.png that Outlook embeds — these are
                  the rendered green-bg headshots from the mockup itself
                  and we ignore them).

The parser:

* Returns the message-level subject and sender (used to derive product,
  year, month, language).
* Splits the body into ``editor_notes_html`` (everything before the
  preview table) and ``preview_html`` (the inner content of that table).
* Returns attachments as raw bytes — but skips the ``image00X.png``
  inline previews that aren't real headshots.

The parser does NOT understand individual slots — that's `ai_extractor`'s
job. It only handles the structural envelope.
"""

from __future__ import annotations

import email
import re
from email import policy
from pathlib import Path
from typing import IO, List, Tuple, Union

from bs4 import BeautifulSoup

from builder.models import EmlAttachment, ParsedEml

# Mock-email widths used by the request authors.  The shipped Korean and FV
# mockups all use width="600"; we accept a few sensible variants.
_PREVIEW_WIDTH_CANDIDATES = {"600", "598", "595"}

# Filenames Outlook auto-generates for inline images embedded in the message
# body itself — these are NOT real headshot uploads.  We skip them.
_INLINE_PREVIEW_FN_RE = re.compile(r"^image\d{3}\.(png|jpe?g|gif)$", re.IGNORECASE)

# Minimum character length for a table to be considered a newsletter mockup
# (avoids mistaking tiny layout tables for the preview).
_PREVIEW_MIN_TEXT_LEN = 400


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse(source: Union[str, Path, bytes, IO[bytes]]) -> ParsedEml:
    """Parse a `.eml` file and return a `ParsedEml`.

    Accepts a path, raw bytes, or a binary file-like object — handy for
    Streamlit's ``UploadedFile`` (which is a BytesIO subclass).
    """
    msg = _load_message(source)

    subject = msg.get("Subject", "") or ""
    sender = msg.get("From", "") or ""

    html_body = _get_html_body(msg)
    if not html_body:
        raise ValueError("Email has no HTML body — cannot parse a Support Notes request without one.")

    preview_html, editor_notes_html = _split_preview_from_notes(html_body)
    attachments = _collect_attachments(msg)

    return ParsedEml(
        subject_header=subject.strip(),
        sender=sender.strip(),
        preview_html=preview_html,
        editor_notes_html=editor_notes_html,
        attachments=attachments,
    )


# ---------------------------------------------------------------------------
# Message loading
# ---------------------------------------------------------------------------

def _load_message(source: Union[str, Path, bytes, IO[bytes]]):
    """Return an email.message.EmailMessage from any reasonable input."""
    if isinstance(source, (str, Path)):
        with open(source, "rb") as fp:
            return email.message_from_binary_file(fp, policy=policy.default)
    if isinstance(source, bytes):
        return email.message_from_bytes(source, policy=policy.default)
    # File-like (e.g. Streamlit UploadedFile)
    if hasattr(source, "read"):
        data = source.read()
        if isinstance(data, str):
            data = data.encode("utf-8")
        return email.message_from_bytes(data, policy=policy.default)
    raise TypeError(f"Unsupported source type for .eml parse: {type(source)!r}")


def _get_html_body(msg) -> str:
    """Extract the HTML body, decoded as a string."""
    body = msg.get_body(preferencelist=("html",))
    if body is None:
        return ""
    return body.get_content()


# ---------------------------------------------------------------------------
# Preview-table isolation
# ---------------------------------------------------------------------------

def _strip_outlook_quoted_reply(soup) -> None:
    """Remove the Outlook quoted-reply section (and all descendants) from soup in-place.

    Reply emails from Outlook embed the entire previous message thread inside
    a well-known separator element.  Everything from that separator onward is
    old content and must be discarded before we search for the preview table,
    otherwise the parser would treat a quoted PREVIOUS newsletter as the
    preview of the CURRENT request.

    Handles several Outlook HTML patterns:
      • <div id="divRplyFwdMsg">  — modern OWA / Outlook desktop reply header
      • <div id="appendonsend">   — another Outlook reply marker
      • <div>/<p> whose entire visible text is a run of ≥10 underscores —
        the "________" separator line Word/Outlook inserts
      • A <div> or <p> whose inline style contains border-top and whose text
        starts with "From:" — the classic Word-filtered-medium quote header
    """
    # Pattern 1: well-known Outlook reply-separator div IDs
    for sep_id in ("divRplyFwdMsg", "appendonsend", "divTaggedMessageHeader"):
        sep = soup.find(id=sep_id)
        if sep:
            for el in list(sep.find_all_next()):
                el.decompose()
            sep.decompose()
            return

    # Pattern 2: underscore separator line  ("________________")
    for el in soup.find_all(["div", "p"]):
        txt = el.get_text().strip()
        if re.match(r"^_{10,}$", txt):
            for following in list(el.find_all_next()):
                following.decompose()
            el.decompose()
            return

    # Pattern 3: Word "filtered medium" border-top + "From:" block
    for el in soup.find_all(["div", "p"]):
        style = (el.get("style") or "").lower()
        if "border-top" in style and el.get_text(strip=True).startswith("From:"):
            for following in list(el.find_all_next()):
                following.decompose()
            el.decompose()
            return


def _split_preview_from_notes(html: str) -> Tuple[str, str]:
    """Return (preview_html, editor_notes_html).

    Strategy:
      1. Strip any Outlook quoted-reply section so that a quoted previous
         newsletter is not mistaken for the current request's preview.
      2. Find the first outer <table> (no <table> ancestor) whose declared
         width matches one of the email-mockup widths.
      3. Everything before that table = editor notes.
      4. The inner HTML of that table = preview.

    If no suitable preview table is found after stripping quotes, the entire
    body content is treated as editor notes and preview_html is returned as
    an empty string.  The AI extractor handles this case by extracting all
    content from editor notes alone.
    """
    # --- pass 1: strip quoted reply, then search for the preview table ---
    soup = BeautifulSoup(html, "lxml")
    _strip_outlook_quoted_reply(soup)
    reply_stripped = True

    outer_tables = [t for t in soup.find_all("table") if not t.find_parent("table")]

    preview_table = None
    for t in outer_tables:
        if (t.get("width") or "").strip() in _PREVIEW_WIDTH_CANDIDATES:
            preview_table = t
            break

    if preview_table is None and outer_tables:
        # Fallback: the largest outer table — only if it looks like a mockup.
        candidate = max(outer_tables, key=lambda t: len(t.get_text(" ", strip=True)))
        if len(candidate.get_text(" ", strip=True)) >= _PREVIEW_MIN_TEXT_LEN:
            preview_table = candidate

    # If stripping removed all meaningful content, the request content IS the
    # quoted section (e.g. a localisation team replies with the translated
    # newsletter as the entire body, with nothing new above the Outlook
    # separator).  Retry on the full unstripped HTML.
    if preview_table is None and len(soup.get_text(strip=True)) < _PREVIEW_MIN_TEXT_LEN:
        soup = BeautifulSoup(html, "lxml")
        reply_stripped = False
        outer_tables = [t for t in soup.find_all("table") if not t.find_parent("table")]
        for t in outer_tables:
            if (t.get("width") or "").strip() in _PREVIEW_WIDTH_CANDIDATES:
                preview_table = t
                break
        if preview_table is None and outer_tables:
            candidate = max(outer_tables, key=lambda t: len(t.get_text(" ", strip=True)))
            if len(candidate.get_text(" ", strip=True)) >= _PREVIEW_MIN_TEXT_LEN:
                preview_table = candidate

    if preview_table is None:
        # No mockup table found in the new content — treat everything as
        # editor notes and return an empty preview so the AI falls back.
        return "", str(soup)

    # --- pass 2: build editor_notes from a clean copy of the (stripped) html ---
    soup_for_notes = BeautifulSoup(html, "lxml")
    if reply_stripped:
        _strip_outlook_quoted_reply(soup_for_notes)

    notes_pt = None
    for t in soup_for_notes.find_all("table"):
        if t.find_parent("table"):
            continue
        if (t.get("width") or "").strip() in _PREVIEW_WIDTH_CANDIDATES:
            notes_pt = t
            break
    if notes_pt is None:
        outer_in_notes = [
            t for t in soup_for_notes.find_all("table") if not t.find_parent("table")
        ]
        if outer_in_notes:
            candidate = max(outer_in_notes, key=lambda t: len(t.get_text(" ", strip=True)))
            if len(candidate.get_text(" ", strip=True)) >= _PREVIEW_MIN_TEXT_LEN:
                notes_pt = candidate

    if notes_pt is not None:
        for sibling in list(notes_pt.find_all_next()):
            sibling.decompose()
        notes_pt.decompose()
    editor_notes_html = str(soup_for_notes)

    preview_html = preview_table.decode_contents()
    return preview_html, editor_notes_html


# ---------------------------------------------------------------------------
# Attachment collection
# ---------------------------------------------------------------------------

def _collect_attachments(msg) -> List[EmlAttachment]:
    """Collect real attachments — skipping inline preview images."""
    out: List[EmlAttachment] = []
    for part in msg.walk():
        if part.is_multipart():
            continue
        ct = part.get_content_type()
        if ct in ("text/plain", "text/html"):
            continue
        fn = part.get_filename()
        cid_raw = part.get("Content-ID", "")
        cid = cid_raw.strip("<>") if cid_raw else None
        if not fn:
            # Not really useful without a filename; skip.
            continue
        if _INLINE_PREVIEW_FN_RE.match(fn):
            # Inline mockup preview — not a real headshot.  Skip.
            continue
        payload = part.get_payload(decode=True) or b""
        if not payload:
            continue
        out.append(EmlAttachment(filename=fn, content_type=ct, content_id=cid, bytes=payload))
    return out


# ---------------------------------------------------------------------------
# Subject parsing — used by callers to derive product/year/month/language.
# ---------------------------------------------------------------------------

# Korean subjects:    "Tessent 지원 노트 - 2026년 5월"
#                     "Functional Verification 지원 노트 - 2026년 5월"
# English subjects:   "Tessent Support Notes - May 2026"
# Japanese subjects:  "Tessent サポートノート - 2026年5月"
# Chinese (CN/TW):    "Tessent 支持说明 - 2026年5月" / "支援說明 - 2026年5월"
#
# We also tolerate a "[TEST - …]:" prefix that the SFMC-shipped test sends carry.

_SUBJECT_LANG_PATTERNS = [
    # (lang_code, regex)
    ("ko",
     re.compile(r"(?P<product>.+?)\s*지원\s*노트\s*[-–]\s*(?P<year>\d{4})\s*년\s*(?P<month>\d{1,2})\s*월", re.IGNORECASE)),
    ("ja",
     re.compile(r"(?P<product>.+?)\s*サポートノート\s*[-–]\s*(?P<year>\d{4})\s*年\s*(?P<month>\d{1,2})\s*月", re.IGNORECASE)),
    ("zh-CN",
     re.compile(r"(?P<product>.+?)\s*支持说明\s*[-–]\s*(?P<year>\d{4})\s*年\s*(?P<month>\d{1,2})\s*月", re.IGNORECASE)),
    ("zh-TW",
     re.compile(r"(?P<product>.+?)\s*支援說明\s*[-–]\s*(?P<year>\d{4})\s*年\s*(?P<month>\d{1,2})\s*月", re.IGNORECASE)),
    # English — "April 2026" (text month)
    ("en",
     re.compile(r"(?P<product>.+?)\s+Support\s+Notes\s*[-–]\s*(?P<month_name>[A-Za-z]+)\s+(?P<year>\d{4})", re.IGNORECASE)),
    # English — "04.2026" (numeric month.year, used by some teams)
    ("en",
     re.compile(r"(?P<product>.+?)\s+Support\s+Notes\s*[-–]\s*(?P<month>\d{1,2})\.(?P<year>\d{4})", re.IGNORECASE)),
]

_EN_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def parse_subject(subject: str) -> dict:
    """Extract structured fields from the .eml Subject header.

    Returns a dict::

        {"product": "Tessent", "language": "ko", "year": 2026, "month": 5}

    Raises ValueError if the subject doesn't match any known pattern.
    """
    # Strip leading [TEST - ...]: prefix the test send-routes add
    cleaned = re.sub(r"^\s*\[[^\]]+\]\s*:\s*", "", subject).strip()
    # Strip reply/forward prefixes that Outlook prepends (RE:, FW:, FWD:)
    cleaned = re.sub(r"^\s*(?:RE|FW|FWD)\s*:", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)

    for lang, pat in _SUBJECT_LANG_PATTERNS:
        m = pat.search(cleaned)
        if not m:
            continue
        gd = m.groupdict()
        product = gd["product"].strip()
        year = int(gd["year"])
        if "month_name" in gd and gd.get("month_name"):
            month = _EN_MONTHS.get(gd["month_name"].lower())
            if not month:
                continue
        else:
            month = int(gd["month"])
        return {"product": product, "language": lang, "year": year, "month": month}

    raise ValueError(f"Could not parse Support Notes subject: {subject!r}")
