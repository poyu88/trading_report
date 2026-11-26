"""Phase 2：獨立 C 層財務標準答案（合成資料；不得用受測 FIFO／Projector）。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from backend.golden import expected_c as ec


def test_golden_module_must_not_import_under_test_fifo_or_projector() -> None:
    """C 層模組不得依賴受測 FIFO／報表投影。"""
    import ast

    tree = ast.parse(Path(ec.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            imported.add(mod)
            for alias in node.names:
                imported.add(f"{mod}.{alias.name}" if mod else alias.name)
    forbidden_prefixes = (
        "backend.services.fifo_matcher",
        "backend.services.allocation_service",
        "backend.services.report_finance",
        "backend.services.report_service",
        "backend.services.detail_projector",
    )
    for name in imported:
        for prefix in forbidden_prefixes:
            assert not name.startswith(prefix), f"C layer must not import {name}"


def test_aggregate_source_finance_from_valid_rows() -> None:
    rows = [
        {
            "symbol": "2236",
            "trade_date": "2024/8/5",
            "side": "BUY",
            "side_raw": "現股買進",
            "quantity": "1000",
            "unit_price": "100",
            "gross_amount": "100000",
            "commission": "100",
            "tax": "0",
            "interest": "0",
            "net_settlement": "-100100",
            "physical_line": 3,
        },
        {
            "symbol": "2236",
            "trade_date": "2024/8/6",
            "side": "SELL",
            "side_raw": "現股賣出",
            "quantity": "400",
            "unit_price": "110",
            "gross_amount": "44000",
            "commission": "40",
            "tax": "130",
            "interest": "0",
            "net_settlement": "43830",
            "physical_line": 4,
        },
    ]
    agg = ec.aggregate_source_finance(rows)
    assert agg["valid_trade_count"] == 2
    assert agg["buy_trade_count"] == 1
    assert agg["sell_trade_count"] == 1
    assert agg["buy_quantity"] == "1000"
    assert agg["sell_quantity"] == "400"
    assert agg["buy_gross_amount"] == "100000"
    assert agg["sell_gross_amount"] == "44000"
    assert agg["buy_commission"] == "100"
    assert agg["sell_commission"] == "40"
    assert agg["tax"] == "130"
    assert agg["interest"] == "0"
    assert agg["net_settlement"] == "-56270"
    assert agg["fee_landing_policy"] == "source_values_unsplit"


def test_independent_cash_fifo_two_pass_same_day() -> None:
    """Pass1 不用當日買解套；Pass2 同日補沖銷。"""
    trades = [
        ec.ExpectedTrade(
            trade_id="S1",
            symbol="2236",
            trade_date=date(2024, 8, 5),
            side="SELL",
            quantity=400,
            unit_price=Decimal(110),
            gross_amount=Decimal(44000),
            commission=Decimal(40),
            tax=Decimal(130),
            interest=Decimal(0),
            source_order=0,
        ),
        ec.ExpectedTrade(
            trade_id="B1",
            symbol="2236",
            trade_date=date(2024, 8, 5),
            side="BUY",
            quantity=1000,
            unit_price=Decimal(100),
            gross_amount=Decimal(100000),
            commission=Decimal(100),
            tax=Decimal(0),
            interest=Decimal(0),
            source_order=1,
        ),
    ]
    result = ec.independent_cash_fifo(trades, opening_lots=())
    assert result.standard_fifo_allocated_qty == 0
    assert result.same_day_reconciled_qty == 400
    assert result.unmatched_sell_qty == 0
    assert result.unsold_buy_qty == 600
    assert result.blocking_insufficient_prior_buys is False


def test_independent_cash_fifo_no_invented_opening() -> None:
    trades = [
        ec.ExpectedTrade(
            trade_id="S1",
            symbol="2236",
            trade_date=date(2024, 1, 2),
            side="SELL",
            quantity=100,
            unit_price=Decimal(10),
            gross_amount=Decimal(1000),
            commission=Decimal(1),
            tax=Decimal(3),
            interest=Decimal(0),
            source_order=0,
        ),
    ]
    result = ec.independent_cash_fifo(trades, opening_lots=())
    assert result.unmatched_sell_qty == 100
    assert result.blocking_insufficient_prior_buys is True
    assert result.standard_fifo_allocated_qty == 0
    assert result.same_day_reconciled_qty == 0


def test_realized_pnl_and_open_cost_fee_on_first_fragment() -> None:
    trades = [
        ec.ExpectedTrade(
            trade_id="B1",
            symbol="X",
            trade_date=date(2024, 1, 1),
            side="BUY",
            quantity=1000,
            unit_price=Decimal(10),
            gross_amount=Decimal(10000),
            commission=Decimal(20),
            tax=Decimal(0),
            interest=Decimal(0),
            source_order=0,
        ),
        ec.ExpectedTrade(
            trade_id="S1",
            symbol="X",
            trade_date=date(2024, 1, 2),
            side="SELL",
            quantity=400,
            unit_price=Decimal(12),
            gross_amount=Decimal(4800),
            commission=Decimal(10),
            tax=Decimal(14),
            interest=Decimal(0),
            source_order=1,
        ),
    ]
    fifo = ec.independent_cash_fifo(trades, opening_lots=())
    finance = ec.compute_realized_and_open(trades, fifo)
    assert finance["matched_allocated_qty"] == 400
    assert finance["realized_pnl"] == "756"
    assert finance["open_quantity"] == 600
    assert finance["open_cost"] == "6000"
    assert finance["status"] == "COMPUTED"


def test_invalid_row_count_unknown_for_unverified_formats() -> None:
    assert ec.invalid_row_count_status("html_table_xls") == "UNKNOWN"
    assert ec.invalid_row_count_status("esun_xlsx") == "UNKNOWN"
    assert ec.invalid_row_count_status("capital_csv") == "CLASSIFIED"


def test_build_expected_c_document_schema_from_rows() -> None:
    rows = [
        {
            "symbol": "2236",
            "trade_date": "2024/8/5",
            "side": "BUY",
            "side_raw": "現股買進",
            "quantity": "1000",
            "unit_price": "100",
            "gross_amount": "100000",
            "commission": "100",
            "tax": "0",
            "interest": "0",
            "net_settlement": "-100100",
            "physical_line": 3,
            "trade_type": "CASH",
            "currency": "TWD",
        },
        {
            "symbol": "2236",
            "trade_date": "2024/8/5",
            "side": "SELL",
            "side_raw": "現股賣出",
            "quantity": "400",
            "unit_price": "110",
            "gross_amount": "44000",
            "commission": "40",
            "tax": "130",
            "interest": "0",
            "net_settlement": "43830",
            "physical_line": 4,
            "trade_type": "CASH",
            "currency": "TWD",
        },
    ]
    doc = ec.build_expected_c_document(
        case_id="GOLD-SYN",
        source_sha256="a" * 64,
        source_path="synthetic/a.csv",
        source_format="capital_csv",
        applicable_spec=["SPEC.md §6", "SPEC.md §7"],
        rows=rows,
        opening_lots_policy="NONE_APPROVED",
    )
    assert doc["layer"] == "C"
    assert doc["derivation"] == "A_source_plus_SPEC"
    assert doc["case_id"] == "GOLD-SYN"
    assert doc["source_sha256"] == "a" * 64
    assert doc["opening_lots"] == "NONE_APPROVED"
    assert doc["aggregates"]["buy_quantity"] == "1000"
    assert doc["fifo_expected"]["same_day_reconciled_qty"] == 400
    assert doc["fifo_expected"]["algorithm"] == "CASH_TWO_PASS_SPEC_INDEPENDENT"
    assert doc["validation_status"] == "INDEPENDENTLY_COMPUTED"


def test_inventory_html_esun_invalid_defaults_unknown() -> None:
    """HTML／玉山尚未驗證 invalid 分計時不得預設 0。"""
    from scripts._golden_phase01_inventory import unresolved_invalid_row_count

    assert unresolved_invalid_row_count("html_table_xls") == "UNKNOWN"
    assert unresolved_invalid_row_count("esun_xlsx") == "UNKNOWN"
