"""Phase 3 合併前收尾：GOLD-004 判定、CR-10A 重複鍵、CR-10C 守恆內容。"""

from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

from backend.golden.compare_c_d import (
    compare_allocation_lines_to_trace_rows,
    trade_source_fingerprint,
)
from backend.golden.phase3_pipeline import (
    decide_gold004_verdict,
    verify_audit_artifacts_content,
)
from backend.reports.fifo_trace_writer import HEADERS as TRACE_HEADERS


def test_gold004_necessary_failure_is_fail_not_partial() -> None:
    """必要驗收失敗不得因任一項成功而降為 PARTIAL。"""
    result = decide_gold004_verdict(
        compare_ok=False,
        finance_ok=True,
        per_line_ok=True,
        artifacts_ok=True,
        formal_db_untouched=True,
        pending_data=["open_cost_not_verified"],
    )
    assert result["verdict"] == "FAIL"
    assert result["exit_code"] != 0


def test_gold004_formal_db_drift_is_fail() -> None:
    result = decide_gold004_verdict(
        compare_ok=True,
        finance_ok=True,
        per_line_ok=True,
        artifacts_ok=True,
        formal_db_untouched=False,
        pending_data=[],
    )
    assert result["verdict"] == "FAIL"
    assert result["exit_code"] != 0


def test_gold004_finance_fail_is_fail() -> None:
    result = decide_gold004_verdict(
        compare_ok=True,
        finance_ok=False,
        per_line_ok=True,
        artifacts_ok=True,
        formal_db_untouched=True,
        pending_data=[],
    )
    assert result["verdict"] == "FAIL"
    assert result["exit_code"] != 0


def test_gold004_partial_only_when_necessary_ok_and_pending() -> None:
    """PARTIAL 僅限已登記資料不足，且必要驗證全過。"""
    result = decide_gold004_verdict(
        compare_ok=True,
        finance_ok=True,
        per_line_ok=True,
        artifacts_ok=True,
        formal_db_untouched=True,
        pending_data=["open_cost_not_verified"],
    )
    assert result["verdict"] == "PARTIAL"
    assert result["exit_code"] == 0


def test_gold004_full_pass_when_necessary_ok_no_pending() -> None:
    result = decide_gold004_verdict(
        compare_ok=True,
        finance_ok=True,
        per_line_ok=True,
        artifacts_ok=True,
        formal_db_untouched=True,
        pending_data=[],
    )
    assert result["verdict"] == "PASS"
    assert result["exit_code"] == 0


def _fp(side: str, *, qty: int = 100, price: str = "10", gross: str = "1000") -> str:
    return trade_source_fingerprint(
        symbol="2236",
        trade_date="2024-08-05" if side == "BUY" else "2024-08-08",
        side=side,
        quantity=qty,
        unit_price=price,
        gross_amount=gross,
        commission="1",
        tax="0" if side == "BUY" else "3",
        interest="0",
    )


def test_compare_allocation_lines_detects_duplicate_identity_overwrite() -> None:
    """重複配對鍵不得被 dict 覆蓋而遺失；列數必須一致。"""
    buy_fp = _fp("BUY")
    sell_fp = _fp("SELL", price="11", gross="1100")
    line = {
        "match_type": "STANDARD_FIFO",
        "buy_trade_id": "src:b1",
        "sell_trade_id": "src:s1",
        "quantity": 50,
        "cost": "500.5",
        "income": "548",
        "realized_pnl": "47.5",
        "buy_commission_applied": "0.5",
        "sell_commission_applied": "0.5",
        "sell_tax_applied": "1.5",
        "sell_interest_applied": "0",
    }
    expected_c = {
        "trade_fingerprints": [
            {
                "source_trade_id": "src:b1",
                "symbol": "2236",
                "trade_date": "2024-08-05",
                "side": "BUY",
                "quantity": 100,
                "unit_price": "10",
                "gross_amount": "1000",
                "commission": "1",
                "tax": "0",
                "interest": "0",
            },
            {
                "source_trade_id": "src:s1",
                "symbol": "2236",
                "trade_date": "2024-08-08",
                "side": "SELL",
                "quantity": 100,
                "unit_price": "11",
                "gross_amount": "1100",
                "commission": "1",
                "tax": "3",
                "interest": "0",
            },
        ],
        "allocation_lines": [line, dict(line)],  # 兩筆相同 identity
    }
    # Trace 僅一筆 → 覆蓋後看似匹配但列數不符
    trace_rows = [
        {
            "row_kind": "MATCHED",
            "match_type": "STANDARD_FIFO",
            "quantity": 50,
            "buy_trade_id": "db-b",
            "sell_trade_id": "db-s",
            "cost": Decimal("500.5"),
            "income": Decimal(548),
            "profit": Decimal("47.5"),
            "commission": Decimal("0.5"),
            "tax": Decimal("1.5"),
            "interest": Decimal(0),
        }
    ]
    result = compare_allocation_lines_to_trace_rows(
        expected_c,
        trace_rows,
        trade_id_to_fp={"db-b": buy_fp, "db-s": sell_fp},
    )
    assert result["ok"] is False
    assert result["expected_line_count"] == 2
    assert result["actual_matched_count"] == 1
    assert "line_identity_multiset" in result["diffs"] or "duplicate" in str(result).lower()


def test_compare_allocation_lines_duplicate_keys_both_sides_match() -> None:
    buy_fp = _fp("BUY")
    sell_fp = _fp("SELL", price="11", gross="1100")
    line = {
        "match_type": "STANDARD_FIFO",
        "buy_trade_id": "src:b1",
        "sell_trade_id": "src:s1",
        "quantity": 50,
        "cost": "500.5",
        "income": "548",
        "realized_pnl": "47.5",
        "buy_commission_applied": "0.5",
        "sell_commission_applied": "0.5",
        "sell_tax_applied": "1.5",
        "sell_interest_applied": "0",
    }
    expected_c = {
        "trade_fingerprints": [
            {
                "source_trade_id": "src:b1",
                "symbol": "2236",
                "trade_date": "2024-08-05",
                "side": "BUY",
                "quantity": 100,
                "unit_price": "10",
                "gross_amount": "1000",
                "commission": "1",
                "tax": "0",
                "interest": "0",
            },
            {
                "source_trade_id": "src:s1",
                "symbol": "2236",
                "trade_date": "2024-08-08",
                "side": "SELL",
                "quantity": 100,
                "unit_price": "11",
                "gross_amount": "1100",
                "commission": "1",
                "tax": "3",
                "interest": "0",
            },
        ],
        "allocation_lines": [line, dict(line)],
    }
    matched = {
        "row_kind": "MATCHED",
        "match_type": "STANDARD_FIFO",
        "quantity": 50,
        "buy_trade_id": "db-b",
        "sell_trade_id": "db-s",
        "cost": Decimal("500.5"),
        "income": Decimal(548),
        "profit": Decimal("47.5"),
        "commission": Decimal("0.5"),
        "tax": Decimal("1.5"),
        "interest": Decimal(0),
    }
    result = compare_allocation_lines_to_trace_rows(
        expected_c,
        [matched, dict(matched)],
        trade_id_to_fp={"db-b": buy_fp, "db-s": sell_fp},
    )
    assert result["ok"] is True
    assert result["expected_line_count"] == 2
    assert result["actual_matched_count"] == 2


def _write_min_trace(path: Path) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(list(TRACE_HEADERS))
    row = [""] * len(TRACE_HEADERS)
    idx = {h: i for i, h in enumerate(TRACE_HEADERS)}
    row[idx["列語意"]] = "MATCHED"
    row[idx["股票代號"]] = "2236"
    row[idx["股數"]] = 100
    row[idx["手續費"]] = 1
    row[idx["交易稅"]] = 3
    row[idx["利息"]] = 0
    row[idx["成本"]] = 1001
    row[idx["收入"]] = 1096
    row[idx["損益"]] = 95
    row[idx["buy_trade_id"]] = "b"
    row[idx["sell_trade_id"]] = "s"
    row[idx["match_type"]] = "STANDARD_FIFO"
    ws.append(row)
    wb.save(path)


def _write_conservation(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "trade_id",
        "side",
        "source_qty",
        "A_original_gross",
        "F_conservation_ok",
        "commission",
        "tax",
        "interest",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def test_cr10c_conservation_false_row_fails_full_pass(tmp_path: Path) -> None:
    """CSV 出現 F_conservation_ok=False → 不得完整 PASS。"""
    out = tmp_path / "out"
    out.mkdir()
    trace = out / "trace.xlsx"
    cons = out / "cons.csv"
    exc = out / "exc.csv"
    audit_path = out / "audit.json"
    _write_min_trace(trace)
    _write_conservation(
        cons,
        [
            {
                "trade_id": "t1",
                "side": "SELL",
                "source_qty": "100",
                "A_original_gross": "1100",
                "F_conservation_ok": "False",
                "commission": "1",
                "tax": "3",
                "interest": "0",
            }
        ],
    )
    exc.write_text("issue_id,code,severity\n", encoding="utf-8-sig")
    audit_path.write_text(
        json.dumps(
            {
                "conservation_ok": True,  # 與 CSV 不一致
                "fifo_trace_file": str(trace),
                "conservation_file": str(cons),
                "trade_count": 1,
                "allocation_count": 1,
                "draft": False,
            }
        ),
        encoding="utf-8",
    )
    result = verify_audit_artifacts_content(
        audit_path=audit_path, exceptions_path=exc, out_dir=out
    )
    assert result["ok"] is False
    assert result["checks"].get("conservation_all_rows_ok") is False


def test_cr10c_audit_conservation_must_match_csv(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    trace = out / "trace.xlsx"
    cons = out / "cons.csv"
    exc = out / "exc.csv"
    audit_path = out / "audit.json"
    _write_min_trace(trace)
    _write_conservation(
        cons,
        [
            {
                "trade_id": "t1",
                "side": "BUY",
                "source_qty": "100",
                "A_original_gross": "1000",
                "F_conservation_ok": "True",
                "commission": "1",
                "tax": "0",
                "interest": "0",
            }
        ],
    )
    exc.write_text("issue_id,code,severity\n", encoding="utf-8-sig")
    audit_path.write_text(
        json.dumps(
            {
                "conservation_ok": False,
                "fifo_trace_file": str(trace),
                "conservation_file": str(cons),
                "trade_count": 1,
                "allocation_count": 1,
                "draft": False,
            }
        ),
        encoding="utf-8",
    )
    result = verify_audit_artifacts_content(
        audit_path=audit_path, exceptions_path=exc, out_dir=out
    )
    assert result["ok"] is False
    assert result["checks"].get("audit_conservation_matches_rows") is False


def test_cr10c_illegal_conservation_type_fails(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    trace = out / "trace.xlsx"
    cons = out / "cons.csv"
    exc = out / "exc.csv"
    audit_path = out / "audit.json"
    _write_min_trace(trace)
    _write_conservation(
        cons,
        [
            {
                "trade_id": "t1",
                "side": "BUY",
                "source_qty": "100",
                "A_original_gross": "1000",
                "F_conservation_ok": "yes",
                "commission": "1",
                "tax": "0",
                "interest": "0",
            }
        ],
    )
    exc.write_text("issue_id,code,severity\n", encoding="utf-8-sig")
    audit_path.write_text(
        json.dumps(
            {
                "conservation_ok": "ok",  # 非法型別
                "fifo_trace_file": str(trace),
                "conservation_file": str(cons),
                "trade_count": 1,
                "allocation_count": 1,
                "draft": False,
            }
        ),
        encoding="utf-8",
    )
    result = verify_audit_artifacts_content(
        audit_path=audit_path, exceptions_path=exc, out_dir=out
    )
    assert result["ok"] is False
    assert result["checks"].get("audit_conservation_ok_is_bool") is False
    assert result["checks"].get("conservation_ok_values_legal") is False


def test_cr10c_all_true_and_matching_audit_passes(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    trace = out / "trace.xlsx"
    cons = out / "cons.csv"
    exc = out / "exc.csv"
    audit_path = out / "audit.json"
    _write_min_trace(trace)
    _write_conservation(
        cons,
        [
            {
                "trade_id": "t1",
                "side": "BUY",
                "source_qty": "100",
                "A_original_gross": "1000",
                "F_conservation_ok": "True",
                "commission": "1",
                "tax": "0",
                "interest": "0",
            }
        ],
    )
    exc.write_text("issue_id,code,severity\n", encoding="utf-8-sig")
    audit_path.write_text(
        json.dumps(
            {
                "conservation_ok": True,
                "fifo_trace_file": str(trace),
                "conservation_file": str(cons),
                "trade_count": 1,
                "allocation_count": 1,
                "draft": False,
            }
        ),
        encoding="utf-8",
    )
    result = verify_audit_artifacts_content(
        audit_path=audit_path, exceptions_path=exc, out_dir=out
    )
    assert result["ok"] is True
    assert result["checks"]["conservation_all_rows_ok"] is True
    assert result["checks"]["audit_conservation_matches_rows"] is True
