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


@pytest.mark.parametrize("raw", ["NaN", "nan", "Infinity", "Inf", "-Infinity", "-Inf"])
def test_gold_cr06_rejects_non_finite(raw: str) -> None:
    with pytest.raises(ValueError, match="invalid_decimal"):
        normalize_decimal_text(raw)


def test_gold_cr06_same_illegal_text_must_not_compare_equal() -> None:
    """兩個相同非法輸入不得被判定核對成功。"""
    from backend.util.decimal_text import decimal_texts_equal

    assert decimal_texts_equal("not-a-number", "not-a-number") is False
    assert decimal_texts_equal("NaN", "NaN") is False
    assert decimal_texts_equal("11,05", "11,05") is False


def test_gold_cr06_inventory_normalize_num_propagates() -> None:
    from scripts._golden_phase01_inventory import normalize_num, nums_equal

    with pytest.raises(ValueError, match="invalid_decimal"):
        normalize_num("NaN")
    assert nums_equal("bad", "bad") is False
    assert nums_equal("1,105", "1105") is True


def test_gold_cr06_blank_vs_zero_preserved() -> None:
    assert normalize_decimal_text("") == ""
    assert normalize_decimal_text("0") == "0"
    assert normalize_decimal_text("") != normalize_decimal_text("0")


def test_gold_cr07_thousand_sep_and_signed_zero() -> None:
    assert normalize_decimal_text("1,105.00") == "1105"
    assert normalize_decimal_text("+1,030.00") == "1030"
    assert normalize_decimal_text("-0") == "0"
    assert normalize_decimal_text("-0.00") == "0"
    assert normalize_decimal_text("0.0") == "0"
    assert normalize_decimal_text("-4,424.50") == "-4424.5"
    assert normalize_decimal_text("1,105,000") == "1105000"


@pytest.mark.parametrize("raw", ["11,05", "1,,105", ",", " , ", "1,05.00"])
def test_gold_cr07_rejects_illegal_thousand_sep(raw: str) -> None:
    with pytest.raises(ValueError, match="invalid_decimal"):
        normalize_decimal_text(raw)

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
