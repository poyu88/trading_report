"""CR-10：UAT ``build_uat_checks``／Excel 財務驗證不可假性通過。"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

from backend.reports.field_schema import HEADERS
from scripts.uat_fifo_same_day_2236 import (
    TRADES,
    build_uat_checks,
    compute_finance_golden_from_uat_trades,
    verify_detail_xlsx_finance,
)


def _passing_kwargs() -> dict:
    return {
        "required_outputs": {
            "detail_xlsx": True,
            "audit_json": True,
            "exceptions_csv": True,
            "fifo_trace": True,
            "conservation": True,
        },
        "migration_probe": {
            "day_trade_backfill_ok": True,
            "cash_standard_ok": True,
            "foreign_key_check_empty": True,
            "integrity_ok": True,
        },
        "fresh_schema_has_match_type": True,
        "allocated_qty": 4000,
        "qty_by_match_type": {"STANDARD_FIFO": 3600, "SAME_DAY_RECONCILED": 400},
        "unsold_qty": 0,
        "blocking": False,
        "conservation_ok": True,
        "audit_json": {
            "conservation_ok": True,
            "day_trade_annotation": {
                "status": "OK",
                "suspected_day_trade_qty": 1000,
                "same_day_reconciled_qty": 400,
                "warnings": [],
            },
        },
        "integrity_check_result": "ok",
        "h_annotation_non_interference": True,
        "detail_is_draft": False,
        "idempotent": {
            "old_run_preserved": True,
            "old_run_keys_unchanged": True,
            "new_run_keys_equal_old": True,
            "allocated_qty_same": True,
        },
        "formal_db_untouched": True,
        "run_dir_under_data_uat": True,
        "out_dir_under_output_uat": True,
        "detail_xlsx_finance_ok": True,
    }


def test_build_uat_checks_all_pass_on_normal_fixture() -> None:
    """正常 fixture → all(checks) True。"""
    checks = build_uat_checks(**_passing_kwargs())
    assert checks
    assert all(checks.values())


def test_build_uat_checks_requires_detail_xlsx_finance_ok() -> None:
    """CR-10A：未提供 detail_xlsx_finance_ok → 不得預設 True 通過。"""
    kwargs = deepcopy(_passing_kwargs())
    del kwargs["detail_xlsx_finance_ok"]
    with pytest.raises(TypeError):
        build_uat_checks(**kwargs)


def test_build_uat_checks_detail_xlsx_finance_false_fails() -> None:
    """CR-10A：detail_xlsx_finance_ok=False → all(checks) False。"""
    kwargs = deepcopy(_passing_kwargs())
    kwargs["detail_xlsx_finance_ok"] = False
    checks = build_uat_checks(**kwargs)
    assert checks["detail_xlsx_finance_ok"] is False
    assert all(checks.values()) is False


def test_build_uat_checks_missing_annotation_warnings_key_fails() -> None:
    """CR-10C：audit annotation 缺 warnings 鍵 → FAIL（不得當成空 warnings）。"""
    kwargs = deepcopy(_passing_kwargs())
    del kwargs["audit_json"]["day_trade_annotation"]["warnings"]
    checks = build_uat_checks(**kwargs)
    assert checks["annotation_has_warnings_key"] is False
    assert checks["annotation_warnings_empty"] is False
    assert all(checks.values()) is False


@pytest.mark.parametrize(
    "mutate,fail_key",
    [
        (lambda k: k["required_outputs"].__setitem__("fifo_trace", False), "required_fifo_trace"),
        (
            lambda k: k["required_outputs"].__setitem__("conservation", False),
            "required_conservation",
        ),
        (lambda k: k["required_outputs"].__setitem__("audit_json", False), "required_audit_json"),
        (lambda k: k["audit_json"].__setitem__("conservation_ok", False), "audit_json_conservation_ok"),
        (
            lambda k: k["audit_json"]["day_trade_annotation"].__setitem__("status", "FAILED"),
            "annotation_status_ok",
        ),
        (
            lambda k: k["audit_json"]["day_trade_annotation"].__setitem__(
                "suspected_day_trade_qty", 999
            ),
            "annotation_suspected_exact_1000",
        ),
        (
            lambda k: k["audit_json"]["day_trade_annotation"].__setitem__(
                "same_day_reconciled_qty", 0
            ),
            "annotation_reconciled_exact_400",
        ),
        (
            lambda k: k["audit_json"]["day_trade_annotation"].__setitem__(
                "warnings", ["ANNOTATION_FAILED:X"]
            ),
            "annotation_warnings_empty",
        ),
        (
            lambda k: k["migration_probe"].__setitem__("cash_standard_ok", False),
            "actual_migration_cash_standard_ok",
        ),
        (
            lambda k: k["migration_probe"].__setitem__("day_trade_backfill_ok", False),
            "actual_migration_day_trade_backfill",
        ),
        (lambda k: k.__setitem__("formal_db_untouched", False), "formal_db_untouched"),
        (
            lambda k: k["idempotent"].__setitem__("old_run_keys_unchanged", False),
            "idempotent_old_keys_unchanged",
        ),
        (lambda k: k.__setitem__("conservation_ok", False), "conservation_ok"),
        (lambda k: k.__setitem__("detail_is_draft", True), "not_draft"),
        (lambda k: k.__setitem__("blocking", True), "not_blocking"),
        (lambda k: k.__setitem__("detail_xlsx_finance_ok", False), "detail_xlsx_finance_ok"),
    ],
)
def test_build_uat_checks_reverse_failures(mutate, fail_key: str) -> None:
    """刻意注入失敗 → all(checks) 為 False，且對應鍵為 False。"""
    kwargs = deepcopy(_passing_kwargs())
    mutate(kwargs)
    checks = build_uat_checks(**kwargs)
    assert fail_key in checks
    assert checks[fail_key] is False
    assert all(checks.values()) is False


def test_build_uat_checks_missing_required_outputs_empty_fails() -> None:
    """缺 required_outputs → 不可假性通過。"""
    kwargs = deepcopy(_passing_kwargs())
    kwargs["required_outputs"] = {}
    checks = build_uat_checks(**kwargs)
    assert checks["required_outputs_all"] is False
    assert all(checks.values()) is False


def _write_minimal_detail_xlsx(path: Path, *, profit: Decimal = Decimal(28618)) -> Path:
    """寫入具備 HEADERS 的最小明細（僅一列賣出費用／損益）。"""
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    for col, header in enumerate(HEADERS, start=1):
        ws.cell(1, col, header)
    idx = {h: i + 1 for i, h in enumerate(HEADERS)}
    # 將 golden 全部分攤到一列（驗證加總路徑）
    golden = compute_finance_golden_from_uat_trades(TRADES)
    ws.cell(2, idx["手續費（買）"], float(golden["buy_commission"]))
    ws.cell(2, idx["手續費（賣）"], float(golden["sell_commission"]))
    ws.cell(2, idx["交易稅"], float(golden["tax"]))
    ws.cell(2, idx["成本"], float(golden["buy_gross"] + golden["buy_commission"]))
    # income - cost == profit；調整 income 使 profit 參數生效
    cost = golden["buy_gross"] + golden["buy_commission"]
    income = cost + profit
    ws.cell(2, idx["收入"], float(income))
    ws.cell(2, idx["損益"], float(profit))
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def test_verify_detail_xlsx_finance_ok_on_matching_totals(tmp_path: Path) -> None:
    """CR-10A：Excel 財務加總與 golden 一致 → ok。"""
    golden = compute_finance_golden_from_uat_trades(TRADES)
    path = _write_minimal_detail_xlsx(tmp_path / "ok.xlsx", profit=golden["expected_report_profit"])
    result = verify_detail_xlsx_finance(path, golden)
    assert result["ok"] is True
    assert result["diffs"] == {}


def test_verify_detail_xlsx_finance_fails_when_profit_off_by_one(tmp_path: Path) -> None:
    """CR-10A：損益差 1 元 → ok=False，diffs 記錄。"""
    golden = compute_finance_golden_from_uat_trades(TRADES)
    path = _write_minimal_detail_xlsx(
        tmp_path / "bad_profit.xlsx",
        profit=golden["expected_report_profit"] + Decimal(1),
    )
    result = verify_detail_xlsx_finance(path, golden)
    assert result["ok"] is False
    assert "profit" in result["diffs"]


def test_verify_detail_xlsx_finance_fails_missing_file(tmp_path: Path) -> None:
    """CR-10A：檔案不存在 → fail-closed。"""
    golden = compute_finance_golden_from_uat_trades(TRADES)
    result = verify_detail_xlsx_finance(tmp_path / "missing.xlsx", golden)
    assert result["ok"] is False
    assert "missing_file" in result["errors"]


def test_verify_detail_xlsx_finance_fails_blank_workbook(tmp_path: Path) -> None:
    """CR-10A：空白／無表頭 Excel → fail-closed。"""
    path = tmp_path / "blank.xlsx"
    Workbook().save(path)
    golden = compute_finance_golden_from_uat_trades(TRADES)
    result = verify_detail_xlsx_finance(path, golden)
    assert result["ok"] is False


def test_verify_detail_xlsx_finance_fails_unreadable(tmp_path: Path) -> None:
    """CR-10A：無法讀取的檔案 → fail-closed。"""
    path = tmp_path / "corrupt.xlsx"
    path.write_bytes(b"not-an-xlsx")
    golden = compute_finance_golden_from_uat_trades(TRADES)
    result = verify_detail_xlsx_finance(path, golden)
    assert result["ok"] is False
    assert result["errors"]


def test_compute_finance_golden_from_uat_trades_independent() -> None:
    """Golden 由 TRADES 以 Decimal 獨立核算（非硬編碼常數）。"""
    golden = compute_finance_golden_from_uat_trades(TRADES)
    assert golden["buy_qty"] == 4000
    assert golden["sell_qty"] == 4000
    assert golden["buy_commission"] == Decimal(90)  # 40+25+25
    assert golden["sell_commission"] == Decimal(135)  # 20+30+30+30+20+5
    assert golden["tax"] == Decimal(1178)
    assert golden["expected_report_profit"] == (
        golden["sell_gross"] - golden["buy_gross"] - golden["commission"] - golden["tax"]
    )
