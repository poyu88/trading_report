"""CR-10：UAT ``build_uat_checks``／Excel 財務驗證不可假性通過。"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

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
    """寫入單列灌總額明細（結構不足；僅供 RED-05 反例）。"""
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    for col, header in enumerate(HEADERS, start=1):
        ws.cell(1, col, header)
    idx = {h: i + 1 for i, h in enumerate(HEADERS)}
    golden = compute_finance_golden_from_uat_trades(TRADES)
    cost = golden["buy_gross"] + golden["buy_commission"]
    income = cost + profit
    ws.cell(2, idx["股數（買）"], float(golden["buy_qty"]))
    ws.cell(2, idx["股數（賣）"], float(golden["sell_qty"]))
    ws.cell(2, idx["手續費（買）"], float(golden["buy_commission"]))
    ws.cell(2, idx["手續費（賣）"], float(golden["sell_commission"]))
    ws.cell(2, idx["交易稅"], float(golden["tax"]))
    ws.cell(2, idx["利息"], 0)
    ws.cell(2, idx["成本"], float(cost))
    ws.cell(2, idx["收入"], float(income))
    ws.cell(2, idx["損益"], float(profit))
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def _write_matching_multi_row_detail_xlsx(
    path: Path,
    *,
    profit: Decimal | None = None,
    n_rows: int | None = None,
) -> Path:
    """寫入多列合成明細，財務加總對齊 golden（正向／竄改基底）。

    將買賣股數、費用、成本、收入、損益均勻拆到 ``n_rows``（預設＝賣出筆數），
    殘差放末列，確保加總精確。禁止以單列總額冒充完整報表。
    """
    golden = compute_finance_golden_from_uat_trades(TRADES)
    rows = n_rows if n_rows is not None else int(golden.get("min_detail_rows", 6))
    if rows < 1:
        raise ValueError("n_rows must be >= 1")
    profit_total = (
        profit if profit is not None else golden["expected_report_profit"]
    )
    cost_total = golden.get("cost", golden["buy_gross"] + golden["buy_commission"])
    income_total = golden.get("income", cost_total + profit_total)
    # 若呼叫端覆寫 profit，同步調整 income 以維持恒等式
    if profit is not None:
        income_total = cost_total + profit_total

    def _split(total: Decimal) -> list[Decimal]:
        base = (total / rows).quantize(Decimal("0.01"))
        parts = [base] * (rows - 1)
        parts.append(total - sum(parts))
        return parts

    buy_qtys = _split(golden["buy_qty"])
    sell_qtys = _split(golden["sell_qty"])
    buy_comms = _split(golden["buy_commission"])
    sell_comms = _split(golden["sell_commission"])
    taxes = _split(golden["tax"])
    interests = _split(golden.get("interest", Decimal(0)))
    costs = _split(cost_total)
    incomes = _split(income_total)
    profits = _split(profit_total)

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    for col, header in enumerate(HEADERS, start=1):
        ws.cell(1, col, header)
    idx = {h: i + 1 for i, h in enumerate(HEADERS)}
    for i in range(rows):
        r = i + 2
        ws.cell(r, idx["股數（買）"], float(buy_qtys[i]))
        ws.cell(r, idx["股數（賣）"], float(sell_qtys[i]))
        ws.cell(r, idx["手續費（買）"], float(buy_comms[i]))
        ws.cell(r, idx["手續費（賣）"], float(sell_comms[i]))
        ws.cell(r, idx["交易稅"], float(taxes[i]))
        ws.cell(r, idx["利息"], float(interests[i]))
        ws.cell(r, idx["成本"], float(costs[i]))
        ws.cell(r, idx["收入"], float(incomes[i]))
        ws.cell(r, idx["損益"], float(profits[i]))
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def _mutate_xlsx_column_sum(
    path: Path,
    column: str,
    *,
    delta: Decimal,
) -> None:
    """將指定欄第一個非空儲存格加上 delta（供竄改案例）。"""
    wb = load_workbook(path)
    ws = wb.active
    assert ws is not None
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    idx = {h: i for i, h in enumerate(headers)}
    for row in ws.iter_rows(min_row=2, max_col=len(headers)):
        cell = row[idx[column]]
        if cell.value is not None:
            cell.value = float(Decimal(str(cell.value)) + delta)
            break
    wb.save(path)


def test_verify_detail_xlsx_finance_ok_on_matching_totals(tmp_path: Path) -> None:
    """CR-10A：多列合成明細財務加總與 golden 一致 → ok（禁止單列灌總額）。"""
    golden = compute_finance_golden_from_uat_trades(TRADES)
    path = _write_matching_multi_row_detail_xlsx(tmp_path / "ok.xlsx")
    result = verify_detail_xlsx_finance(path, golden)
    assert result["ok"] is True
    assert result["diffs"] == {}


def test_verify_detail_xlsx_finance_fails_when_profit_off_by_one(tmp_path: Path) -> None:
    """CR-10A：損益差 1 元 → ok=False，diffs 記錄。"""
    golden = compute_finance_golden_from_uat_trades(TRADES)
    path = _write_matching_multi_row_detail_xlsx(
        tmp_path / "bad_profit.xlsx",
        profit=golden["expected_report_profit"] + Decimal(1),
    )
    result = verify_detail_xlsx_finance(path, golden)
    assert result["ok"] is False
    assert "profit" in result["diffs"]


def test_verify_detail_xlsx_finance_fails_when_cost_income_both_up(tmp_path: Path) -> None:
    """RED-01：cost+1 且 income+1（profit 不變）→ 須獨立抓到 cost／income。"""
    golden = compute_finance_golden_from_uat_trades(TRADES)
    path = _write_matching_multi_row_detail_xlsx(tmp_path / "cost_income_up.xlsx")
    _mutate_xlsx_column_sum(path, "成本", delta=Decimal(1))
    _mutate_xlsx_column_sum(path, "收入", delta=Decimal(1))
    result = verify_detail_xlsx_finance(path, golden)
    assert result["ok"] is False
    assert "cost" in result["diffs"] or "income" in result["diffs"]


def test_verify_detail_xlsx_finance_fails_when_cost_income_both_down(tmp_path: Path) -> None:
    """RED-02：cost-1 且 income-1（profit 不變）→ 須獨立抓到 cost／income。"""
    golden = compute_finance_golden_from_uat_trades(TRADES)
    path = _write_matching_multi_row_detail_xlsx(tmp_path / "cost_income_down.xlsx")
    _mutate_xlsx_column_sum(path, "成本", delta=Decimal(-1))
    _mutate_xlsx_column_sum(path, "收入", delta=Decimal(-1))
    result = verify_detail_xlsx_finance(path, golden)
    assert result["ok"] is False
    assert "cost" in result["diffs"] or "income" in result["diffs"]


def test_verify_detail_xlsx_finance_fails_when_buy_qty_tampered(tmp_path: Path) -> None:
    """RED-03：竄改股數（買）合計 → diffs 含 buy_qty。"""
    golden = compute_finance_golden_from_uat_trades(TRADES)
    path = _write_matching_multi_row_detail_xlsx(tmp_path / "buy_qty.xlsx")
    _mutate_xlsx_column_sum(path, "股數（買）", delta=Decimal(1))
    result = verify_detail_xlsx_finance(path, golden)
    assert result["ok"] is False
    assert "buy_qty" in result["diffs"]


def test_verify_detail_xlsx_finance_fails_when_sell_qty_tampered(tmp_path: Path) -> None:
    """RED-04：竄改股數（賣）合計 → diffs 含 sell_qty。"""
    golden = compute_finance_golden_from_uat_trades(TRADES)
    path = _write_matching_multi_row_detail_xlsx(tmp_path / "sell_qty.xlsx")
    _mutate_xlsx_column_sum(path, "股數（賣）", delta=Decimal(1))
    result = verify_detail_xlsx_finance(path, golden)
    assert result["ok"] is False
    assert "sell_qty" in result["diffs"]


def test_verify_detail_xlsx_finance_rejects_single_row_fake_totals(tmp_path: Path) -> None:
    """RED-05：單列灌總額不得冒充完整報表（data_rows／結構下限）。"""
    golden = compute_finance_golden_from_uat_trades(TRADES)
    path = _write_minimal_detail_xlsx(
        tmp_path / "single_row_fake.xlsx",
        profit=golden["expected_report_profit"],
    )
    result = verify_detail_xlsx_finance(path, golden)
    assert result["ok"] is False
    assert (
        "data_rows" in result["diffs"]
        or "min_detail_rows" in result["diffs"]
        or any("data_rows" in e or "min_detail" in e for e in result["errors"])
    )


def test_verify_detail_xlsx_finance_fails_when_finance_cells_cleared(tmp_path: Path) -> None:
    """RED-06：保留表頭、清空成本／收入／股數等必要儲存格 → fail-closed。"""
    golden = compute_finance_golden_from_uat_trades(TRADES)
    path = _write_matching_multi_row_detail_xlsx(tmp_path / "cleared.xlsx")
    wb = load_workbook(path)
    ws = wb.active
    assert ws is not None
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    idx = {h: i for i, h in enumerate(headers)}
    clear_cols = ["股數（買）", "股數（賣）", "成本", "收入", "利息"]
    for row in ws.iter_rows(min_row=2, max_col=len(headers)):
        for col in clear_cols:
            row[idx[col]].value = None
    wb.save(path)
    result = verify_detail_xlsx_finance(path, golden)
    assert result["ok"] is False


def test_verify_detail_xlsx_finance_fails_when_per_row_offsets_cancel(
    tmp_path: Path,
) -> None:
    """RED-07：逐筆成本／收入互抵但總額不變 → 須以 per_row golden FAIL。"""
    golden = compute_finance_golden_from_uat_trades(TRADES)
    path = _write_matching_multi_row_detail_xlsx(tmp_path / "per_row.xlsx")
    # 讀出合法逐筆作為 golden
    wb = load_workbook(path, data_only=True)
    ws = wb.active
    assert ws is not None
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    idx = {h: i for i, h in enumerate(headers)}
    costs: list[Decimal] = []
    incomes: list[Decimal] = []
    for row in ws.iter_rows(min_row=2, max_col=len(headers), values_only=True):
        if all(v is None for v in row):
            continue
        costs.append(Decimal(str(row[idx["成本"]] or 0)))
        incomes.append(Decimal(str(row[idx["收入"]] or 0)))
    golden = {
        **golden,
        "per_row_costs": costs,
        "per_row_incomes": incomes,
    }
    assert verify_detail_xlsx_finance(path, golden)["ok"] is True

    # 列 0 +1、列 1 -1 → 總額不變
    wb2 = load_workbook(path)
    ws2 = wb2.active
    assert ws2 is not None
    headers2 = [c.value for c in next(ws2.iter_rows(min_row=1, max_row=1))]
    idx2 = {h: i + 1 for i, h in enumerate(headers2)}
    r0_cost = ws2.cell(2, idx2["成本"])
    r1_cost = ws2.cell(3, idx2["成本"])
    r0_income = ws2.cell(2, idx2["收入"])
    r1_income = ws2.cell(3, idx2["收入"])
    r0_cost.value = float(Decimal(str(r0_cost.value)) + Decimal(1))
    r1_cost.value = float(Decimal(str(r1_cost.value)) - Decimal(1))
    r0_income.value = float(Decimal(str(r0_income.value)) + Decimal(1))
    r1_income.value = float(Decimal(str(r1_income.value)) - Decimal(1))
    wb2.save(path)

    result = verify_detail_xlsx_finance(path, golden)
    assert result["ok"] is False
    assert "per_row_costs" in result["diffs"] or "per_row_incomes" in result["diffs"]


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
    assert golden["interest"] == Decimal(0)
    assert golden["cost"] == golden["buy_gross"] + golden["buy_commission"]
    assert golden["income"] == (
        golden["sell_gross"]
        - golden["sell_commission"]
        - golden["tax"]
        - golden["interest"]
    )
    assert golden["unsold_qty"] == Decimal(0)
    assert golden["remaining_inventory_cost"] == Decimal(0)
    assert golden["min_detail_rows"] == Decimal(6)
    assert golden["expected_report_profit"] == (
        golden["sell_gross"] - golden["buy_gross"] - golden["commission"] - golden["tax"]
    )
    assert golden["expected_report_profit"] == golden["income"] - golden["cost"]
