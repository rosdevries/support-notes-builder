"""Data model for a Support Notes email.

The pipeline is:

    .eml ──► eml_parser ──► (raw HTML preview, attachments, headers)
                                │
                                ▼
                          ai_extractor ──► SupportNotesData
                                │
                                ▼
                          slot_renderer ──► dict[slot_key, html_string]
                                │
                                ▼
                          email_builder ──► SFMC htmlemail asset

`SupportNotesData` is the intermediate representation that the user reviews
and edits in the Streamlit UI. It contains exactly the per-product, per-month
fields documented in `docs/slot-inventory.md` — nothing more.

Static slots (intro, footer, footnote, etc.) are NOT part of this model;
they live in `templates/static_slots.py` and are dropped in unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Optional


# ---------------------------------------------------------------------------
# Sub-records
# ---------------------------------------------------------------------------

@dataclass
class Speaker:
    """A featured speaker / engineer for one editorial section."""

    name: str = ""               # localised, e.g. "윤의상 이사"
    title: str = "Applications Engineer"  # almost always this exact title
    photo_url: str = ""          # SFMC CDN URL after upload, empty until uploaded


@dataclass
class Article:
    """A single article link row in a resource column.

    Used for both the left column (KBA / document links) and the right column
    (related articles, webinar recordings, tag chips).  Each section can carry
    any number of articles in each column.
    """

    label: str = ""         # visible link text
    url: str = ""
    icon_name: str = ""     # library icon name (e.g. "kba", "docs"); empty = column default


# Backwards-compatible alias — old code that referenced KbaTag still works.
KbaTag = Article


@dataclass
class EditorialSection:
    """One of the two product-editorial blocks on the page (section1 / section2)."""

    quote: str = ""                  # the question headline
    editorial_html: str = ""         # the editorial paragraph (may include <strong> etc)
    speaker: Speaker = field(default_factory=Speaker)
    left_articles: List[Article] = field(default_factory=list)   # left column links
    right_articles: List[Article] = field(default_factory=list)  # right column links


@dataclass
class WebinarHighlight:
    """One entry in the upcoming-webinars list in section3."""

    date_label: str = ""             # e.g. "5/7" or "May 7"
    title: str = ""                  # webinar title
    url: str = ""                    # registration / recording link (optional)


@dataclass
class ReleaseHighlight:
    """The 'latest release' download row in section3.

    For Tessent this is typically a single row: ``Tessent 2026.1-p1``.
    For Functional Verification it's multiple components, e.g.::

        Questa Core/Prime/One 2026.1_1
        Questa Verification IP 2026.1_1
        Avery Verification IP 2026.1_1
        ...

    Each entry pairs the human-readable label with the download URL.
    """

    components: List["ReleaseComponent"] = field(default_factory=list)


@dataclass
class ReleaseComponent:
    label: str = ""
    url: str = ""


# ---------------------------------------------------------------------------
# Top-level record
# ---------------------------------------------------------------------------

@dataclass
class SupportNotesData:
    """Everything that varies month-to-month for one Support Notes email.

    Compose-once, edit in the UI, render to slots, ship to SFMC.
    """

    # --- Identity --------------------------------------------------------
    product: str = ""                # "Tessent" | "Functional Verification"
    language: str = "ko"             # language code: ko / en / ja / zh-CN / zh-TW
    year: int = 0                    # 2026
    month: int = 0                   # 1..12

    # --- Header ----------------------------------------------------------
    header_title: str = ""           # localised, e.g. "TESSENT 지원 노트"
    header_strapline: str = ""       # localised, e.g. "유용한 Tessent™ 팁과…"
    subscribe_url: str = ""          # the "구독신청" button link target
    subscribe_button_text: str = ""  # overrides the language-default label when set

    # --- Editorials ------------------------------------------------------
    section1: EditorialSection = field(default_factory=EditorialSection)
    section2: EditorialSection = field(default_factory=EditorialSection)

    # --- Section 3 (right-rail callouts) --------------------------------
    upcoming_webinars: List[WebinarHighlight] = field(default_factory=list)
    webinar_series_url: str = ""     # the "Tessent 한국어 웨비나 시리즈" link
    promo_block_html: str = ""       # optional discount-code / promo paragraph
    latest_release: ReleaseHighlight = field(default_factory=ReleaseHighlight)

    # --- Subject + preheader --------------------------------------------
    subject: str = ""                # full localised subject line
    preheader: str = ""              # short preview text (≤ ~85 chars)

    # --- Overridable static blocks --------------------------------------
    # When empty the renderer falls back to the defaults in static_slots.py.
    contact_body_html: str = ""      # section3contactdetails static part — support-centre text
    webinar_header_html: str = ""    # "Got more questions?" intro sentence — overrides phrase template when set
    footnote_html: str = ""          # section3fullwidth2 — archive links footnote
    footer_html: str = ""            # footertext — legal / address / unsubscribe

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SupportNotesData":
        # Rehydrate nested dataclasses
        d = dict(d)
        d["section1"] = _section_from_dict(d.get("section1") or {})
        d["section2"] = _section_from_dict(d.get("section2") or {})

        # upcoming_webinars: support old singular key from pre-refactor drafts
        if "upcoming_webinar" in d and "upcoming_webinars" not in d:
            old = d.pop("upcoming_webinar")
            d["upcoming_webinars"] = [WebinarHighlight(**(old or {}))]
        else:
            d.pop("upcoming_webinar", None)
            d["upcoming_webinars"] = [
                WebinarHighlight(**w)
                for w in (d.get("upcoming_webinars") or [])
            ]

        d["latest_release"] = ReleaseHighlight(
            components=[
                ReleaseComponent(**c) for c in (d.get("latest_release") or {}).get("components", [])
            ]
        )
        return cls(**d)


def _section_from_dict(d: dict) -> EditorialSection:
    spk = Speaker(**(d.get("speaker") or {}))

    # Support old format that stored a single `resource` dict
    if "resource" in d and "left_articles" not in d and "right_articles" not in d:
        res = d.get("resource") or {}
        left_articles = []
        if res.get("article_name"):
            left_articles = [Article(label=res["article_name"], url=res.get("article_url", ""))]
        right_articles = [
            Article(label=t.get("label", ""), url=t.get("url", ""))
            for t in (res.get("tags") or [])
        ]
    else:
        left_articles = [
            Article(label=a.get("label", ""), url=a.get("url", ""), icon_name=a.get("icon_name", ""))
            for a in (d.get("left_articles") or [])
        ]
        right_articles = [
            Article(label=a.get("label", ""), url=a.get("url", ""), icon_name=a.get("icon_name", ""))
            for a in (d.get("right_articles") or [])
        ]

    return EditorialSection(
        quote=d.get("quote", ""),
        editorial_html=d.get("editorial_html", ""),
        speaker=spk,
        left_articles=left_articles,
        right_articles=right_articles,
    )


# ---------------------------------------------------------------------------
# Raw .eml parse result — what eml_parser returns to ai_extractor.
# ---------------------------------------------------------------------------

@dataclass
class ParsedEml:
    """Raw structured output of the .eml parser."""

    subject_header: str              # the .eml's Subject header (gives product + month/year)
    sender: str                      # the From address
    preview_html: str                # the inner HTML of the email-mockup table
    editor_notes_html: str           # the editor's instruction block (KBA link pairs etc)
    attachments: List["EmlAttachment"] = field(default_factory=list)


@dataclass
class EmlAttachment:
    filename: str
    content_type: str
    content_id: Optional[str]
    bytes: bytes
