"""GOLD-CR-01／06／07／08／09 最小修正（匿名純函式；非真實帳戶驗收）。

SOURCE: SYNTHETIC_UNIT — 非真實帳戶驗收。
"""

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


def test_gold_cr06_invalid_norm_key_unique_and_json_serializable() -> None:
    """非法鍵不得互撞，且可 JSON 序列化（含原文便於除錯）。"""
    import json

    from scripts._golden_phase01_inventory import _norm_num_key

    a = _norm_num_key("not-a-number")
    b = _norm_num_key("not-a-number")
    assert a != b
    payload = {"keys": [list(a) if isinstance(a, tuple) else a, list(b) if isinstance(b, tuple) else b]}
    dumped = json.dumps(payload, ensure_ascii=False)
    assert "not-a-number" in dumped
    assert "__INVALID_DECIMAL__" in dumped
    json.loads(dumped)


def test_gold_cr03_fingerprint_drift_includes_wal_shm() -> None:
    """DB／WAL／SHM 存在、大小、指紋須納入前後漂移比較。"""
    from scripts._golden_phase01_inventory import compare_fingerprint_bundles

    before = {
        "files": {
            "trading_db": {
                "exists": True,
                "sha256": "a" * 64,
                "file_size_bytes": 100,
                "sidecar-wal": {
                    "exists": True,
                    "sha256": "b" * 64,
                    "file_size_bytes": 10,
                },
                "sidecar-shm": None,
            }
        }
    }
    after_ok = {
        "files": {
            "trading_db": {
                "exists": True,
                "sha256": "a" * 64,
                "file_size_bytes": 100,
                "sidecar-wal": {
                    "exists": True,
                    "sha256": "b" * 64,
                    "file_size_bytes": 10,
                },
                "sidecar-shm": None,
            }
        }
    }
    after_wal_changed = {
        "files": {
            "trading_db": {
                "exists": True,
                "sha256": "a" * 64,
                "file_size_bytes": 100,
                "sidecar-wal": {
                    "exists": True,
                    "sha256": "c" * 64,
                    "file_size_bytes": 11,
                },
                "sidecar-shm": None,
            }
        }
    }
    ok = compare_fingerprint_bundles(before, after_ok)
    assert ok["status"] == "PASS"
    assert ok["drifts"] == []
    bad = compare_fingerprint_bundles(before, after_wal_changed)
    assert bad["status"] == "BLOCKER"
    assert any("sidecar-wal" in str(d) or d.get("part") == "sidecar-wal" for d in bad["drifts"])


def test_gold_cr04_git_security_audit_uses_git_commands() -> None:
    """GOLD-CR-04：須實際跑 git ls-files，不得只看 .gitignore 文字。"""
    from scripts._golden_phase01_inventory import git_security_audit

    result = git_security_audit()
    assert "tracked_sensitive_paths" in result
    assert "tracked_ignored" in result
    assert "commands" in result
    assert "command_results" in result
    assert any("git ls-files" in c for c in result["commands"])
    assert all("returncode" in r for r in result["command_results"])
    assert result["status"] in {"PASS", "FAIL"}
    # 本機乾淨樹：敏感路徑不應被追蹤
    assert result["tracked_sensitive_paths"] == []
    assert result["status"] == "PASS"


def test_gold_cr04_git_security_audit_nonzero_returncode_is_fail() -> None:
    """Git 指令失敗時不得因 stdout 空而 PASS。"""
    from types import SimpleNamespace

    from scripts._golden_phase01_inventory import git_security_audit

    def fake_runner(cmd, **kwargs):
        return SimpleNamespace(returncode=128, stdout="", stderr="fatal: not a git repository")

    result = git_security_audit(runner=fake_runner)
    assert result["status"] == "FAIL"
    assert result["command_failures"]
    assert result["command_failures"][0]["returncode"] == 128
    assert "fatal" in result["command_failures"][0]["stderr"]


def test_gold_cr10_non_blank_row_not_automatically_valid() -> None:
    """GOLD-CR-10：非空白列須通過基本合法性；缺欄／非法數值不得算有效交易。"""
    from scripts._golden_phase01_inventory import classify_capital_csv_row

    blank = classify_capital_csv_row([""] * 10, physical_line=3)
    assert blank["status"] == "blank"

    total = classify_capital_csv_row(["總合(1)"] + [""] * 9, physical_line=4)
    assert total["status"] == "excluded"

    bad_side = classify_capital_csv_row(
        ["2330 台積電", "2024/1/2", "未知別", "臺幣", "100", "1000", "100000", "0", "0", "0"],
        physical_line=5,
    )
    assert bad_side["status"] == "invalid"

    bad_qty = classify_capital_csv_row(
        ["2330 台積電", "2024/1/2", "現股買進", "臺幣", "100", "0", "0", "0", "0", "0"],
        physical_line=6,
    )
    assert bad_qty["status"] == "invalid"

    ok = classify_capital_csv_row(
        ["2330 台積電", "2024/1/2", "現股買進", "臺幣", "100", "1,000", "100,000", "50", "0", "-100,050"],
        physical_line=7,
    )
    assert ok["status"] == "valid"
    assert ok["side"] == "BUY"
    assert ok["trade_type"] == "CASH"
    assert ok["currency"] == "TWD"
    assert ok["quantity"] == "1000"


def test_gold_cr10_invalid_rows_separated_and_block_acceptance() -> None:
    """非法列與排除列分計；有非法列時即使有效列對上 DB 也不得完整 PASS。"""
    import sqlite3

    from scripts._golden_phase01_inventory import (
        build_capital_csv_analysis_from_rows,
        cross_check_csv_to_db,
        csv_acceptance_gate,
    )

    rows = [
        ["商品", "成交日", "買賣別", "幣別", "成交價", "成交股數", "成交金額", "手續費", "交易稅", "淨收付"],
        ["", "", "", "", "", "", "", "", "", ""],
        ["2330 台積電", "2024/1/2", "現股買進", "臺幣", "100", "1,000", "100,000", "50", "0", "-100,050"],
        ["2330 台積電", "2024/1/3", "未知別", "臺幣", "100", "1,000", "100,000", "50", "0", "-100,050"],
        ["總合(1)", "", "", "", "", "", "", "", "", ""],
    ]
    analysis = build_capital_csv_analysis_from_rows(
        rows, source_path="synthetic/capital.csv", header_row_count=2
    )
    assert analysis["valid_trade_count"] == 1
    assert analysis["excluded_row_count"] == 1
    assert analysis["invalid_row_count"] == 1
    inv = analysis["invalid_rows"][0]
    assert inv["physical_line"] == 4
    assert inv["source_path"] == "synthetic/capital.csv"
    assert "invalid_side" in inv["reason"]
    gate = csv_acceptance_gate(analysis)
    assert gate["status"] == "FAIL"
    assert gate["reason"] == "invalid_trade_rows_present"

    sha = "c" * 64
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(
        """
        CREATE TABLE import_batches (
            id TEXT, account_id TEXT, file_sha256 TEXT, filename TEXT,
            profile_id TEXT, profile_version INT, status TEXT
        );
        CREATE TABLE raw_rows (
            id TEXT, batch_id TEXT, row_index INT, row_sha256 TEXT,
            parse_status TEXT, error_code TEXT
        );
        CREATE TABLE trades (
            id TEXT, raw_row_id TEXT, account_id TEXT, symbol TEXT, name TEXT,
            trade_date TEXT, side TEXT, trade_type TEXT, currency TEXT, quantity INT,
            unit_price_txt TEXT, gross_amount_txt TEXT, commission_txt TEXT,
            tax_txt TEXT, interest_txt TEXT, net_settlement_txt TEXT
        );
        """
    )
    con.execute(
        "INSERT INTO import_batches VALUES (?,?,?,?,?,?,?)",
        ("batch1", "acc1", sha, "y.csv", "statement_html_v1", 1, "completed"),
    )
    con.execute(
        "INSERT INTO raw_rows VALUES (?,?,?,?,?,?)",
        ("raw1", "batch1", 3, "d" * 64, "ok", None),
    )
    con.execute(
        "INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "t1",
            "raw1",
            "acc1",
            "2330",
            "台積電",
            "2024-01-02",
            "BUY",
            "CASH",
            "TWD",
            1000,
            "100",
            "100000",
            "50",
            "0",
            "0",
            "-100050",
        ),
    )
    result = cross_check_csv_to_db(analysis, con, file_sha256=sha)
    assert result["matched_count"] == 1
    assert result["status"] == "FAIL"
    assert result["reason"] == "invalid_trade_rows_present"
    assert result["invalid_row_count"] == 1


def test_gold_cr11_ambiguous_batches_must_not_pick_first() -> None:
    """GOLD-CR-11：同 file_sha256 多批次 → AMBIGUOUS，不得 fetchone 偷選。"""
    import sqlite3

    from scripts._golden_phase01_inventory import resolve_batches_by_sha256

    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute(
        """
        CREATE TABLE import_batches (
            id TEXT, account_id TEXT, file_sha256 TEXT, filename TEXT,
            profile_id TEXT, profile_version INT, status TEXT
        )
        """
    )
    sha = "f" * 64
    con.execute(
        "INSERT INTO import_batches VALUES (?,?,?,?,?,?,?)",
        ("b1", "a1", sha, "f.csv", "statement_html_v1", 1, "completed"),
    )
    con.execute(
        "INSERT INTO import_batches VALUES (?,?,?,?,?,?,?)",
        ("b2", "a2", sha, "f.csv", "statement_html_v1", 1, "completed"),
    )
    result = resolve_batches_by_sha256(con, sha)
    assert result["status"] == "AMBIGUOUS"
    assert len(result["batches"]) == 2
    assert result.get("batch") is None


def test_gold_cr05_cross_check_includes_derivable_fields() -> None:
    """GOLD-CR-05：可立即核對 trade_type／currency／account／列序／parse_status。"""
    import sqlite3

    from scripts._golden_phase01_inventory import cross_check_csv_to_db

    sha = "a" * 64
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(
        """
        CREATE TABLE import_batches (
            id TEXT, account_id TEXT, file_sha256 TEXT, filename TEXT,
            profile_id TEXT, profile_version INT, status TEXT
        );
        CREATE TABLE raw_rows (
            id TEXT, batch_id TEXT, row_index INT, row_sha256 TEXT,
            parse_status TEXT, error_code TEXT
        );
        CREATE TABLE trades (
            id TEXT, raw_row_id TEXT, account_id TEXT, symbol TEXT, name TEXT,
            trade_date TEXT, side TEXT, trade_type TEXT, currency TEXT, quantity INT,
            unit_price_txt TEXT, gross_amount_txt TEXT, commission_txt TEXT,
            tax_txt TEXT, interest_txt TEXT, net_settlement_txt TEXT
        );
        """
    )
    con.execute(
        "INSERT INTO import_batches VALUES (?,?,?,?,?,?,?)",
        ("batch1", "acc1", sha, "y.csv", "statement_html_v1", 1, "completed"),
    )
    con.execute(
        "INSERT INTO raw_rows VALUES (?,?,?,?,?,?)",
        ("raw1", "batch1", 3, "b" * 64, "ok", None),
    )
    con.execute(
        "INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "t1",
            "raw1",
            "acc1",
            "2330",
            "台積電",
            "2024-01-02",
            "BUY",
            "CASH",
            "TWD",
            1000,
            "100",
            "100000",
            "50",
            "0",
            "0",
            "-100050",
        ),
    )
    csv_analysis = {
        "valid_trade_count": 1,
        "rows": [
            {
                "physical_line": 3,
                "symbol": "2330",
                "trade_date": "2024/1/2",
                "side_raw": "現股買進",
                "currency_raw": "臺幣",
                "unit_price": "100",
                "quantity": "1,000",
                "gross_amount": "100,000",
                "commission": "50",
                "tax": "0",
                "interest": "0",
                "net_settlement": "-100,050",
                "side": "BUY",
                "trade_type": "CASH",
                "currency": "TWD",
            }
        ],
    }
    result = cross_check_csv_to_db(csv_analysis, con, file_sha256=sha)
    assert result["status"] == "PASS"
    fields = result["matches"][0]["fields"]
    assert fields["trade_type"]["ok"] is True
    assert fields["currency"]["ok"] is True
    assert fields["account_id"]["ok"] is True
    assert fields["parse_status"]["ok"] is True
    assert fields["source_row_order"]["csv"] == 3
    assert fields["source_row_order"]["db"] == 3
    assert fields["raw_row_id"]["csv"] == "NOT_IN_SOURCE"
