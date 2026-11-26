"""GOLD-CR-01／06／07／08／09 最小修正（匿名純函式；非真實帳戶驗收）。"""

from __future__ import annotations

from datetime import date

import pytest

from backend.util.date_text import date_bounds, parse_flexible_date
from backend.util.decimal_text import normalize_decimal_text
from backend.util.sha256_lock import assert_sha256_lock, sha256_lock_mismatches


def test_gold_cr01_date_bounds_not_lexicographic() -> None:
    """字串 min/max 會把 2024/10/1 排在 2024/1/19 之前；須依真實日期。"""
    dates = ["2024/10/1", "2024/1/19", "2024/3/5"]
    lo, hi = date_bounds(dates)
    assert lo == date(2024, 1, 19)
    assert hi == date(2024, 10, 1)
    assert parse_flexible_date("2024-08-05") == date(2024, 8, 5)


def test_gold_cr01_date_bounds_empty_is_none() -> None:
    assert date_bounds([]) == (None, None)
    assert date_bounds(["", "  "]) == (None, None)


def test_gold_cr06_illegal_decimal_raises() -> None:
    with pytest.raises(ValueError, match="invalid_decimal"):
        normalize_decimal_text("not-a-number")
    with pytest.raises(ValueError, match="invalid_decimal"):
        normalize_decimal_text("12.34.56")


def test_gold_cr07_thousand_sep_and_signed_zero() -> None:
    assert normalize_decimal_text("1,105.00") == "1105"
    assert normalize_decimal_text("+1,030.00") == "1030"
    assert normalize_decimal_text("-0") == "0"
    assert normalize_decimal_text("-0.00") == "0"
    assert normalize_decimal_text("0.0") == "0"
    assert normalize_decimal_text("-4,424.50") == "-4424.5"


def test_gold_cr08_sha256_lock_detects_mismatch() -> None:
    expected = {
        "a": "0" * 64,
        "b": "1" * 64,
    }
    actual = {
        "a": "0" * 64,
        "b": "2" * 64,
    }
    bad = sha256_lock_mismatches(expected, actual)
    assert bad == ["b"]
    with pytest.raises(ValueError, match="sha256_lock_mismatch"):
        assert_sha256_lock(expected, actual)


def test_gold_cr08_sha256_lock_pass() -> None:
    expected = {"a": "ab" * 32}
    actual = {"a": "ab" * 32}
    assert sha256_lock_mismatches(expected, actual) == []
    assert_sha256_lock(expected, actual)


def test_gold_cr09_inventory_exit_code_helper() -> None:
    """失敗／阻礙必須對應非零結束碼（純函式）。"""
    from scripts._golden_phase01_inventory import inventory_exit_code

    assert inventory_exit_code(blockers=[], inv_fail=False) == 0
    assert inventory_exit_code(blockers=["x"], inv_fail=False) == 1
    assert inventory_exit_code(blockers=[], inv_fail=True) == 1
