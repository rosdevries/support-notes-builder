"""Persist per-email field edits so re-imports don't lose user corrections.

Drafts are keyed by ``{product_slug}_{language}_{year}_{month}`` and stored
as JSON files in the project-level ``drafts/`` directory.  They survive
server restarts and new .eml uploads for the same email identity, so manual
corrections (e.g. fixing broken links supplied by the translation team) are
automatically reapplied whenever the same email combination is re-imported.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from builder.models import SupportNotesData

DRAFTS_DIR = Path(__file__).resolve().parent.parent / "drafts"


def _key(data: SupportNotesData) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (data.product or "").lower()).strip("_")
    return f"{slug}_{data.language}_{data.year}_{data.month}"


def _identifiable(data: SupportNotesData) -> bool:
    return bool(data.product and data.language and data.year and data.month)


def save(data: SupportNotesData) -> None:
    """Write current SupportNotesData to disk, keyed by its identity."""
    if not _identifiable(data):
        return
    DRAFTS_DIR.mkdir(exist_ok=True)
    (DRAFTS_DIR / f"{_key(data)}.json").write_text(
        json.dumps(data.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load(data: SupportNotesData) -> Optional[SupportNotesData]:
    """Return saved draft matching `data`'s identity, or None if none exists."""
    if not _identifiable(data):
        return None
    path = DRAFTS_DIR / f"{_key(data)}.json"
    if not path.exists():
        return None
    try:
        return SupportNotesData.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return None


def delete(data: SupportNotesData) -> None:
    """Remove the saved draft for this identity so the next import starts fresh."""
    if not _identifiable(data):
        return
    path = DRAFTS_DIR / f"{_key(data)}.json"
    if path.exists():
        path.unlink()


def key_display(data: SupportNotesData) -> str:
    return _key(data) if _identifiable(data) else "(unidentified)"
