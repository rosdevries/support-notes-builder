"""Tests for builder.eml_parser — subject parsing and preview/notes split.

Run with: pytest tests/test_eml_parser.py
"""

import pytest

from builder import eml_parser


@pytest.mark.parametrize(
    "subject,expected",
    [
        ("Tessent 지원 노트 - 2026년 5월",
         {"product": "Tessent", "language": "ko", "year": 2026, "month": 5}),
        ("Functional Verification 지원 노트 - 2026년 4월",
         {"product": "Functional Verification", "language": "ko", "year": 2026, "month": 4}),
        ("[TEST - Send amends and approvals to Ros]: Tessent 지원 노트 - 2026년 4월",
         {"product": "Tessent", "language": "ko", "year": 2026, "month": 4}),
        ("Tessent サポートノート - 2026年5月",
         {"product": "Tessent", "language": "ja", "year": 2026, "month": 5}),
        ("Tessent 支持说明 - 2026年5月",
         {"product": "Tessent", "language": "zh-CN", "year": 2026, "month": 5}),
        ("Tessent 支援說明 - 2026年5月",
         {"product": "Tessent", "language": "zh-TW", "year": 2026, "month": 5}),
        ("Tessent Support Notes - May 2026",
         {"product": "Tessent", "language": "en", "year": 2026, "month": 5}),
        ("Functional Verification Support Notes - January 2026",
         {"product": "Functional Verification", "language": "en", "year": 2026, "month": 1}),
    ],
)
def test_parse_subject(subject, expected):
    assert eml_parser.parse_subject(subject) == expected


def test_parse_subject_unrecognised_raises():
    with pytest.raises(ValueError):
        eml_parser.parse_subject("Random unrelated email")


def test_parse_subject_handles_tab_whitespace():
    """The FV May .eml has a tab character after 'Subject:'."""
    s = "\tFunctional Verification 지원 노트 - 2026년 5월"
    result = eml_parser.parse_subject(s)
    assert result["product"] == "Functional Verification"
    assert result["month"] == 5
