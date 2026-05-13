"""Tests for builder.bootstrap_template and the lang-injection now in email_builder.

The bootstrap CLI no longer injects per-language <html lang="..."> — that
responsibility shifted to email_builder.render_html() so the single shared
template stays language-agnostic.  These tests verify both sides of that split.

Run with: pytest tests/test_bootstrap_template.py
"""

import re
import pytest

from builder import bootstrap_template, email_builder
from builder.models import SupportNotesData


# ---------------------------------------------------------------------------
# bootstrap_template: template sanity checks
# ---------------------------------------------------------------------------

def test_template_has_html_lang_attribute():
    """The shared template must have <html lang="..."> for email_builder to patch."""
    html = bootstrap_template.TEMPLATE_PATH.read_text(encoding="utf-8")
    assert re.search(r'<html\b[^>]*\blang="[^"]+"', html), \
        "<html lang=...> not found in template"


def test_template_has_exactly_one_html_tag():
    html = bootstrap_template.TEMPLATE_PATH.read_text(encoding="utf-8")
    assert html.count("<html ") == 1


def test_template_name_constant():
    assert bootstrap_template.TEMPLATE_NAME == "Support Notes - Email template"


# ---------------------------------------------------------------------------
# email_builder: lang injection per language (moved from bootstrap_template)
# ---------------------------------------------------------------------------

def _render_minimal(lang_code: str) -> str:
    """Render a near-empty SupportNotesData just to exercise the lang injection."""
    from datetime import date
    today = date.today()
    data = SupportNotesData(
        product="Tessent", language=lang_code,
        year=today.year, month=today.month,
    )
    return email_builder.render_html(data)["html"]


@pytest.mark.parametrize("code,expected_lang", [
    ("ko", "ko-kr"),
    ("en", "en"),
    ("ja", "ja-jp"),
    ("zh-CN", "zh-cn"),
    ("zh-TW", "zh-tw"),
])
def test_render_html_injects_correct_lang(code, expected_lang):
    html = _render_minimal(code)
    m = re.search(r'<html\b[^>]*\blang="([^"]+)"', html)
    assert m, f"<html lang=...> not found in rendered HTML for {code}"
    assert m.group(1) == expected_lang, (
        f"For {code}: expected lang='{expected_lang}', got '{m.group(1)}'"
    )


def test_render_html_replaces_only_one_lang_occurrence():
    html = _render_minimal("ko")
    assert html.count("<html ") == 1
    assert 'lang="ko-kr"' in html


def test_render_html_unknown_language_raises():
    with pytest.raises(ValueError):
        _render_minimal("fr")
