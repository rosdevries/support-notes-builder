"""Persist the user's icon choices for the three configurable email icon slots.

Each slot maps to a CDN URL (the image used in the rendered email) and
optionally the library icon name that generated it.

Slots
-----
* ``kba_left``  — document icon, left column of KBA resource rows
* ``kba_right`` — tag icon, right column of KBA resource rows
* ``contact``   — envelope icon in the Section 3 contact block

Config is stored as ``data/icon_config.json`` relative to the project root.
The original SFMC CDN URLs are kept as fallback defaults so the app works
out-of-the-box without any icon setup.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

_CONFIG_PATH = Path("data") / "icon_config.json"

SLOTS = ("kba_left", "kba_right", "contact")

# Original shipped URLs — used as fallback until the user picks alternatives.
DEFAULT_URLS: dict[str, str] = {
    "kba_left": (
        "https://image.s7.sfmc-content.com/lib/fe8e13737761047472/m/1"
        "/f2421ea4-9aa2-419b-b1fd-1116543e5a9b.png"
    ),
    "kba_right": (
        "https://image.s7.sfmc-content.com/lib/fe8e13737761047472/m/1"
        "/43d67312-b5a6-480e-a131-2f59032cb0b9.png"
    ),
    "contact": (
        "https://image.s7.sfmc-content.com/lib/fe8e13737761047472/m/1"
        "/c7a0de2b-0bca-468e-ba5f-6c9e46882ca6.png"
    ),
}


def _read() -> dict:
    if _CONFIG_PATH.exists():
        try:
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def get_url(slot: str) -> str:
    """Return the CDN URL currently configured for `slot`."""
    return _read().get(slot, {}).get("url") or DEFAULT_URLS[slot]


def get_name(slot: str) -> Optional[str]:
    """Return the library icon name for `slot`, or None if using default/custom."""
    return _read().get(slot, {}).get("name")


def set_icon(slot: str, *, url: str, name: Optional[str] = None) -> None:
    """Persist icon choice (CDN URL + optional library name) for `slot`."""
    cfg = _read()
    cfg[slot] = {"name": name, "url": url}
    _CONFIG_PATH.parent.mkdir(exist_ok=True)
    _CONFIG_PATH.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_all() -> dict[str, dict]:
    """Return ``{slot: {"name": str|None, "url": str}}`` for all slots."""
    cfg = _read()
    return {
        slot: {
            "name": cfg.get(slot, {}).get("name"),
            "url": cfg.get(slot, {}).get("url") or DEFAULT_URLS[slot],
        }
        for slot in SLOTS
    }


# ---------------------------------------------------------------------------
# Per-icon-name URL cache (for per-article icon assignment)
# ---------------------------------------------------------------------------

_ICON_KEY_PREFIX = "icon:"


def get_url_for_icon(icon_name: str) -> str:
    """Return the cached SFMC CDN URL for a named icon, or '' if not yet uploaded."""
    return _read().get(f"{_ICON_KEY_PREFIX}{icon_name}", {}).get("url") or ""


def set_url_for_icon(icon_name: str, url: str) -> None:
    """Persist a CDN URL for a named icon so subsequent renders reuse it."""
    cfg = _read()
    cfg[f"{_ICON_KEY_PREFIX}{icon_name}"] = {"url": url}
    _CONFIG_PATH.parent.mkdir(exist_ok=True)
    _CONFIG_PATH.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )
