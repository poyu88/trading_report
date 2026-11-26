"""匿名合成：Decimal 文字正規化（GOLD／CSV↔DB 交叉核對用）。

SOURCE: SYNTHETIC_UNIT — 純函式。
"""

from __future__ import annotations

import pytest

from backend.util.decimal_text import normalize_decimal_text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1105.00", "1105"),
        ("1105", "1105"),
        ("1,105.00", "1105"),
        ("-4,424", "-4424"),
        ("-4424.50", "-4424.5"),
        ("0", "0"),
        ("0.00", "0"),
        ("", ""),
        ("  96.80  ", "96.8"),
        ("-0", "0"),
        ("+0.00", "0"),
    ],
)
def test_normalize_decimal_text_anonymous_cases(raw: str, expected: str) -> None:
    assert normalize_decimal_text(raw) == expected


def test_normalize_decimal_text_trailing_zeros_do_not_break_equality() -> None:
    """INV-03／GOLD-004：CSV 尾隨 .00 與 DB 整數文字須視為同一值。"""
    assert normalize_decimal_text("1030.00") == normalize_decimal_text("1030")
    assert normalize_decimal_text("1,030.00") == normalize_decimal_text("1030")


def test_normalize_decimal_text_illegal_raises() -> None:
    """GOLD-CR-06：非法數值不得回傳原文冒充可比對。"""
    with pytest.raises(ValueError, match="invalid_decimal"):
        normalize_decimal_text("not-a-number")
