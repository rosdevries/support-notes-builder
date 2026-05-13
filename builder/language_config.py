"""Per-language configuration for the Support Notes builder.

Each `LanguageConfig` bundles together:

* The HTML `lang=` attribute the rendered email must declare.
* The SFMC Content Builder folder ID where the rendered email asset is created.
* The SFMC template asset ID (set by the bootstrap script).
* Strings that appear verbatim in every email of that language but differ
  between languages — e.g. the subject template, the "지원 노트" suffix, the
  "구독신청" CTA label, footer copy.

Language codes use the conventional BCP-47 short forms used in our SFMC
folder structure: ``en``, ``ko``, ``ja``, ``zh-CN``, ``zh-TW``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class LanguageConfig:
    """Settings that vary by Support Notes language."""

    code: str               # short code: "ko", "en", "ja", "zh-CN", "zh-TW"
    label: str              # human-readable, e.g. "Korean"
    html_lang: str          # value for <html lang="..."> e.g. "ko-kr"
    email_folder_env: str   # env var holding the email folder ID
    template_id_env: str    # env var holding the template asset ID
    # Per-language formatting helpers
    subject_template: str   # e.g. "{product} 지원 노트 - {year}년 {month}월"
    suffix_label: str       # e.g. "지원 노트" — what appears after the product name


# ---------------------------------------------------------------------------
# Registry — the single source of truth for languages we support.
# ---------------------------------------------------------------------------

LANGUAGES: Dict[str, LanguageConfig] = {
    "ko": LanguageConfig(
        code="ko",
        label="Korean",
        html_lang="ko-kr",
        email_folder_env="MC_EMAIL_FOLDER_ID_KO",
        template_id_env="MC_TEMPLATE_ID_KO",
        subject_template="{product} 지원 노트 - {year}년 {month}월",
        suffix_label="지원 노트",
    ),
    "en": LanguageConfig(
        code="en",
        label="English",
        html_lang="en",
        email_folder_env="MC_EMAIL_FOLDER_ID_EN",
        template_id_env="MC_TEMPLATE_ID_EN",
        subject_template="{product} Support Notes - {month_name} {year}",
        suffix_label="Support Notes",
    ),
    "ja": LanguageConfig(
        code="ja",
        label="Japanese",
        html_lang="ja-jp",
        email_folder_env="MC_EMAIL_FOLDER_ID_JP",
        template_id_env="MC_TEMPLATE_ID_JP",
        subject_template="{product} サポートノート - {year}年{month}月",
        suffix_label="サポートノート",
    ),
    "zh-CN": LanguageConfig(
        code="zh-CN",
        label="Simplified Chinese",
        html_lang="zh-cn",
        email_folder_env="MC_EMAIL_FOLDER_ID_ZH_CN",
        template_id_env="MC_TEMPLATE_ID_ZH_CN",
        subject_template="{product} 支持说明 - {year}年{month}月",
        suffix_label="支持说明",
    ),
    "zh-TW": LanguageConfig(
        code="zh-TW",
        label="Traditional Chinese",
        html_lang="zh-tw",
        email_folder_env="MC_EMAIL_FOLDER_ID_ZH_TW",
        template_id_env="MC_TEMPLATE_ID_ZH_TW",
        subject_template="{product} 支援說明 - {year}年{month}月",
        suffix_label="支援說明",
    ),
}


def get(code: str) -> LanguageConfig:
    """Return the LanguageConfig for `code`, raising a clear error if unknown."""
    if code not in LANGUAGES:
        raise ValueError(
            f"Unknown language code {code!r}. "
            f"Known codes: {sorted(LANGUAGES.keys())}"
        )
    return LANGUAGES[code]


def email_folder_id(lang: LanguageConfig) -> int:
    """Resolve the email folder ID from environment for the given language.

    Raises if the env var is not set — we never want to silently default to
    the wrong language's folder.
    """
    raw = os.environ.get(lang.email_folder_env, "").strip()
    if not raw:
        raise RuntimeError(
            f"Email folder for {lang.label} is not configured. "
            f"Set {lang.email_folder_env} in environment / Streamlit secrets."
        )
    return int(raw)


def template_id(lang: LanguageConfig) -> int | None:
    """Resolve the template asset ID, or None if unbootstrapped.

    Checks ``MC_TEMPLATE_ID`` first (single shared template), then falls back
    to the per-language ``MC_TEMPLATE_ID_*`` env var for legacy configs.
    """
    global_raw = os.environ.get("MC_TEMPLATE_ID", "").strip()
    if global_raw:
        return int(global_raw)
    lang_raw = os.environ.get(lang.template_id_env, "").strip()
    if lang_raw:
        return int(lang_raw)
    return None
