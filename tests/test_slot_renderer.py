"""Tests for builder.slot_renderer and builder.email_builder.render_html.

These tests exercise the rendering pipeline without hitting SFMC.
Run with: pytest tests/test_slot_renderer.py
"""

import re

import pytest

from builder import email_builder, slot_renderer
from builder.models import (
    Article,
    EditorialSection,
    ReleaseComponent,
    ReleaseHighlight,
    Speaker,
    SupportNotesData,
    WebinarHighlight,
)


@pytest.fixture
def full_data() -> SupportNotesData:
    """A complete, valid Korean Tessent SupportNotesData with no missing fields."""
    return SupportNotesData(
        product="Tessent",
        language="ko",
        year=2026,
        month=5,
        header_title="TESSENT 지원 노트",
        header_strapline="유용한 Tessent™ 팁과 기술이 담긴 월간 뉴스레터입니다.",
        section1=EditorialSection(
            quote="질문 헤드라인입니다.",
            editorial_html="에디토리얼 본문입니다.",
            speaker=Speaker(
                name="배준영 대리",
                title="Applications Engineer",
                photo_url="https://image.s7.sfmc-content.com/lib/x/y.png",
            ),
            left_articles=[
                Article(
                    label="기사 제목",
                    url="https://support.sw.siemens.com/knowledge-base/KB000123_KO",
                ),
            ],
            right_articles=[
                Article(label="태그명", url="https://docs.sw.siemens.com/x"),
            ],
        ),
        section2=EditorialSection(
            quote="두 번째 질문",
            editorial_html="두 번째 에디토리얼.",
            speaker=Speaker(name="이예원 과장", title="Applications Engineer",
                            photo_url="https://image.s7.sfmc-content.com/lib/x/z.png"),
            left_articles=[
                Article(
                    label="두 번째 기사",
                    url="https://support.sw.siemens.com/knowledge-base/KB000456_KO",
                ),
            ],
            right_articles=[
                Article(label="두 번째 태그", url="https://docs.sw.siemens.com/y"),
            ],
        ),
        upcoming_webinars=[WebinarHighlight(date_label="5/7", title="웨비나 제목")],
        webinar_series_url="https://support.sw.siemens.com/MG617021",
        latest_release=ReleaseHighlight(components=[
            ReleaseComponent(label="Tessent 2026.1", url="https://example.com/dl"),
        ]),
        preheader="짧은 미리보기 텍스트",
    )


def test_render_slots_produces_all_keys(full_data):
    out = slot_renderer.render_slots(full_data)
    assert set(out.keys()) == set(slot_renderer.ALL_SLOT_KEYS)


def test_render_slots_no_placeholders_when_complete(full_data):
    out = slot_renderer.render_slots(full_data)
    assert slot_renderer.has_placeholders(out) == []


def test_render_slots_emits_placeholders_for_empty_data():
    """Empty data should emit TODO placeholders, not silently render junk."""
    empty = SupportNotesData(product="Tessent", language="ko", year=2026, month=5)
    out = slot_renderer.render_slots(empty)
    placeholders = slot_renderer.has_placeholders(out)
    # Must include at minimum: header title, strapline, section quotes
    expected = {"headertitle", "headerstrapline",
                "section1quote", "section1editorial",
                "section2quote", "section2editorial"}
    assert expected.issubset(set(placeholders))


def test_render_html_replaces_all_slot_divs(full_data):
    """The rendered HTML must contain no leftover empty slot div markers."""
    rendered = email_builder.render_html(full_data)
    assert "<div data-type=\"slot\"" not in rendered["html"]


def test_render_html_sets_lang_attr(full_data):
    """The output's <html lang="..."> must match the language config."""
    rendered = email_builder.render_html(full_data)
    m = re.search(r'<html\b[^>]*?\blang="([^"]+)"', rendered["html"])
    assert m and m.group(1) == "ko-kr"


def test_render_html_subject_format_korean(full_data):
    rendered = email_builder.render_html(full_data)
    assert rendered["subject"] == "Tessent 지원 노트 - 2026년 5월"
    assert rendered["name"] == rendered["subject"]


def test_render_html_subject_format_english(full_data):
    full_data.language = "en"
    rendered = email_builder.render_html(full_data)
    assert rendered["subject"] == "Tessent Support Notes - May 2026"


def test_render_html_subject_format_japanese(full_data):
    full_data.language = "ja"
    rendered = email_builder.render_html(full_data)
    assert rendered["subject"] == "Tessent サポートノート - 2026年5月"


def test_render_html_lang_attr_for_each_language(full_data):
    expected = {"ko": "ko-kr", "en": "en", "ja": "ja-jp", "zh-CN": "zh-cn", "zh-TW": "zh-tw"}
    for lang, expected_attr in expected.items():
        full_data.language = lang
        rendered = email_builder.render_html(full_data)
        m = re.search(r'<html\b[^>]*?\blang="([^"]+)"', rendered["html"])
        assert m and m.group(1) == expected_attr, f"For {lang}: expected {expected_attr}"


def test_render_html_includes_speaker_photos(full_data):
    rendered = email_builder.render_html(full_data)
    assert "https://image.s7.sfmc-content.com/lib/x/y.png" in rendered["html"]
    assert "https://image.s7.sfmc-content.com/lib/x/z.png" in rendered["html"]


def test_render_html_includes_kba_links(full_data):
    rendered = email_builder.render_html(full_data)
    assert "KB000123_KO" in rendered["html"]
    assert "KB000456_KO" in rendered["html"]


def test_render_html_has_no_unfilled_slots_when_data_complete(full_data):
    rendered = email_builder.render_html(full_data)
    assert rendered["placeholders"] == []


def test_render_multiple_left_articles(full_data):
    """All left-column articles appear in the rendered HTML."""
    full_data.section1.left_articles = [
        Article(label="Article One", url="https://example.com/1"),
        Article(label="Article Two", url="https://example.com/2"),
        Article(label="Article Three", url="https://example.com/3"),
    ]
    out = slot_renderer.render_slots(full_data)
    html = out["section1resourcenamesleftcol"]
    assert "Article One" in html
    assert "Article Two" in html
    assert "Article Three" in html
    assert "example.com/1" in html
    assert "example.com/3" in html


def test_render_multiple_right_articles(full_data):
    """All right-column articles appear in the rendered HTML."""
    full_data.section2.right_articles = [
        Article(label="Tag A", url="https://example.com/a"),
        Article(label="Tag B", url="https://example.com/b"),
    ]
    out = slot_renderer.render_slots(full_data)
    html = out["section2resourcenamesrightcol"]
    assert "Tag A" in html
    assert "Tag B" in html


def test_render_multiple_webinars(full_data):
    """All webinar entries appear as list items in the rendered contact details."""
    full_data.upcoming_webinars = [
        WebinarHighlight(date_label="4/28", title="Webinar Alpha"),
        WebinarHighlight(date_label="5/7",  title="Webinar Beta"),
        WebinarHighlight(date_label="5/19", title="Webinar Gamma"),
    ]
    out = slot_renderer.render_slots(full_data)
    html = out["section3contactdetails"]
    assert "Webinar Alpha" in html
    assert "Webinar Beta" in html
    assert "Webinar Gamma" in html
    assert "4/28" in html
    assert "5/19" in html


def test_from_dict_migrates_old_resource_format():
    """SupportNotesData.from_dict handles drafts saved before the refactor."""
    d = SupportNotesData(
        product="Tessent", language="ko", year=2026, month=4,
        header_title="T", header_strapline="S",
    ).to_dict()
    # Simulate old format: replace left/right_articles with resource dict
    d["section1"] = {
        "quote": "Q",
        "editorial_html": "E",
        "speaker": {"name": "N", "title": "T", "photo_url": ""},
        "resource": {
            "article_name": "Old KBA",
            "article_url": "https://example.com/old",
            "tags": [{"label": "Old Tag", "url": "https://example.com/tag"}],
        },
    }
    d["section2"] = {
        "quote": "", "editorial_html": "", "speaker": {"name": "", "title": "", "photo_url": ""},
        "resource": {"article_name": "", "article_url": "", "tags": []},
    }
    d["upcoming_webinar"] = {"date_label": "5/7", "title": "Old Webinar"}
    d.pop("upcoming_webinars", None)

    restored = SupportNotesData.from_dict(d)
    assert restored.section1.left_articles[0].label == "Old KBA"
    assert restored.section1.left_articles[0].url == "https://example.com/old"
    assert restored.section1.right_articles[0].label == "Old Tag"
    assert restored.upcoming_webinars[0].title == "Old Webinar"
    assert restored.upcoming_webinars[0].date_label == "5/7"
