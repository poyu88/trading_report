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
            "source_id": "syn",
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
            "account_id": "acct_A",
        },
        {
            "source_id": "syn",
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
            "account_id": "acct_A",
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
        expected_source_sha256={"main": "a" * 64},
        actual_source_sha256={"main": "a" * 64},
        invalid_row_count=0,
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


def test_trade_id_uses_source_and_line_and_stays_unique_across_sources() -> None:
    """跨來源串接不得只靠 physical_line，否則 by_id 會覆蓋。"""
    rows = [
        {
            "source_id": "csv_2023",
            "physical_line": 10,
            "symbol": "2236",
            "trade_date": "2023/1/1",
            "side": "BUY",
            "quantity": "100",
            "unit_price": "10",
            "gross_amount": "1000",
            "commission": "1",
            "tax": "0",
            "interest": "0",
            "net_settlement": "-1001",
            "trade_type": "CASH",
            "currency": "TWD",
            "account_id": "acct_A",
        },
        {
            "source_id": "csv_2024",
            "physical_line": 10,
            "symbol": "2236",
            "trade_date": "2024/1/1",
            "side": "BUY",
            "quantity": "200",
            "unit_price": "11",
            "gross_amount": "2200",
            "commission": "2",
            "tax": "0",
            "interest": "0",
            "net_settlement": "-2202",
            "trade_type": "CASH",
            "currency": "TWD",
            "account_id": "acct_A",
        },
    ]
    trades = ec.rows_to_expected_trades(rows)
    ids = [t.trade_id for t in trades]
    assert ids[0] != ids[1]
    assert ids[0].startswith("csv_2023:")
    assert ids[1].startswith("csv_2024:")
    assert ec.trade_ids_unique(trades) is True


def test_trunc_toward_zero_for_negative_values() -> None:
    assert ec.trunc_toward_zero(Decimal("-1.9")) == Decimal(-1)
    assert ec.trunc_toward_zero(Decimal("1.9")) == Decimal(1)
    assert ec.trunc_toward_zero(Decimal("-0.1")) == Decimal(0)


def test_fifo_does_not_cross_currency_or_account() -> None:
    trades = [
        ec.ExpectedTrade(
            trade_id="a:L1",
            symbol="X",
            trade_date=date(2024, 1, 1),
            side="BUY",
            quantity=100,
            unit_price=Decimal(10),
            gross_amount=Decimal(1000),
            commission=Decimal(1),
            tax=Decimal(0),
            interest=Decimal(0),
            source_order=0,
            currency="TWD",
            account_id="A",
        ),
        ec.ExpectedTrade(
            trade_id="b:L2",
            symbol="X",
            trade_date=date(2024, 1, 2),
            side="SELL",
            quantity=100,
            unit_price=Decimal(11),
            gross_amount=Decimal(1100),
            commission=Decimal(1),
            tax=Decimal(3),
            interest=Decimal(0),
            source_order=1,
            currency="USD",
            account_id="A",
        ),
        ec.ExpectedTrade(
            trade_id="c:L3",
            symbol="X",
            trade_date=date(2024, 1, 2),
            side="SELL",
            quantity=100,
            unit_price=Decimal(12),
            gross_amount=Decimal(1200),
            commission=Decimal(1),
            tax=Decimal(3),
            interest=Decimal(0),
            source_order=2,
            currency="TWD",
            account_id="B",
        ),
    ]
    result = ec.independent_cash_fifo(trades, opening_lots=())
    assert result.standard_fifo_allocated_qty == 0
    assert result.same_day_reconciled_qty == 0
    assert result.unmatched_sell_qty == 200
    assert result.unsold_buy_qty == 100


def test_source_integrity_blocks_full_success() -> None:
    gate = ec.evaluate_source_integrity(
        expected_sha256={"csv_2024": "a" * 64},
        actual_sha256={"csv_2024": "b" * 64},
        invalid_row_count=0,
    )
    assert gate["status"] == "FAIL"
    assert "sha256_lock_mismatch" in gate["reasons"][0]

    gate2 = ec.evaluate_source_integrity(
        expected_sha256={"csv_2024": "a" * 64},
        actual_sha256={"csv_2024": "a" * 64},
        invalid_row_count=2,
    )
    assert gate2["status"] == "FAIL"
    assert "invalid_trade_rows_present" in gate2["reasons"]

    gate3 = ec.evaluate_source_integrity(
        expected_sha256={"xls": "a" * 64},
        actual_sha256={"xls": "a" * 64},
        invalid_row_count="UNKNOWN",
    )
    assert gate3["status"] == "PARTIAL"
    assert "invalid_row_count_UNKNOWN_unverified_format" in gate3["reasons"]


def test_document_persists_allocation_lines_and_cash_only_scope() -> None:
    rows = [
        {
            "source_id": "syn",
            "physical_line": 1,
            "symbol": "X",
            "trade_date": "2024/1/1",
            "side": "BUY",
            "quantity": "1000",
            "unit_price": "10",
            "gross_amount": "10000",
            "commission": "20",
            "tax": "0",
            "interest": "0",
            "net_settlement": "-10020",
            "trade_type": "CASH",
            "currency": "TWD",
            "account_id": "acct_A",
        },
        {
            "source_id": "syn",
            "physical_line": 2,
            "symbol": "X",
            "trade_date": "2024/1/2",
            "side": "SELL",
            "quantity": "400",
            "unit_price": "12",
            "gross_amount": "4800",
            "commission": "10",
            "tax": "14",
            "interest": "0",
            "net_settlement": "4776",
            "trade_type": "CASH",
            "currency": "TWD",
            "account_id": "acct_A",
        },
    ]
    doc = ec.build_expected_c_document(
        case_id="GOLD-SYN-LINES",
        source_sha256="a" * 64,
        source_path="synthetic/a.csv",
        source_format="capital_csv",
        applicable_spec=["SPEC.md §6", "SPEC.md §7"],
        rows=rows,
        opening_lots_policy="NONE_APPROVED",
        expected_source_sha256={"main": "a" * 64},
        actual_source_sha256={"main": "a" * 64},
        invalid_row_count=0,
    )
    assert doc["fifo_scope"] == "CASH_ONLY"
    assert len(doc["allocations"]) == 1
    alloc = doc["allocations"][0]
    assert alloc["buy_trade_id"] == "syn:L1"
    assert alloc["sell_trade_id"] == "syn:L2"
    assert alloc["quantity"] == 400
    assert alloc["match_type"] == "STANDARD_FIFO"
    assert alloc["sequence_no"] == 1
    assert len(doc["allocation_lines"]) == 1
    line = doc["allocation_lines"][0]
    assert line["cost"] == "4020"
    assert line["income"] == "4776"
    assert line["buy_commission_applied"] == "20"
    assert line["sell_commission_applied"] == "10"
    assert line["sell_tax_applied"] == "14"
    assert line["gross_conservation_ok"] is True
    assert doc["validation_status"] == "INDEPENDENTLY_COMPUTED"


def test_document_blocked_when_invalid_rows_or_sha_mismatch() -> None:
    rows = [
        {
            "source_id": "syn",
            "physical_line": 1,
            "symbol": "X",
            "trade_date": "2024/1/1",
            "side": "BUY",
            "quantity": "100",
            "unit_price": "10",
            "gross_amount": "1000",
            "commission": "1",
            "tax": "0",
            "interest": "0",
            "net_settlement": "-1001",
            "trade_type": "CASH",
            "currency": "TWD",
            "account_id": "acct_A",
        },
    ]
    doc = ec.build_expected_c_document(
        case_id="GOLD-SYN-BLOCK",
        source_sha256="a" * 64,
        source_path="synthetic/a.csv",
        source_format="capital_csv",
        applicable_spec=["SPEC.md §6"],
        rows=rows,
        opening_lots_policy="NONE_APPROVED",
        expected_source_sha256={"main": "a" * 64},
        actual_source_sha256={"main": "b" * 64},
        invalid_row_count=1,
    )
    assert doc["validation_status"] == "BLOCKED_SOURCE_INTEGRITY"
    assert doc["source_integrity"]["status"] == "FAIL"
    assert len(doc["source_integrity"]["reasons"]) >= 1


def test_amount_out_of_tolerance_marked_not_conserved() -> None:
    result = ec.allocate_fragment_amounts(
        unit_price=Decimal("10.5"),
        gross=Decimal(1000),
        qtys=[50, 50],
    )
    # TRUNC(50*10.5)=525 twice = 1050; diff=-50 > 1
    assert result["conservation_ok"] is False
    assert result["out_of_tolerance"] is True
    assert result["difference"] == "-50"


def test_unknown_interest_marks_partial_not_silent_zero_success() -> None:
    rows = [
        {
            "source_id": "syn",
            "physical_line": 1,
            "symbol": "X",
            "trade_date": "2024/1/1",
            "side": "BUY",
            "quantity": "100",
            "unit_price": "10",
            "gross_amount": "1000",
            "commission": "1",
            "tax": "0",
            "interest": "",
            "net_settlement": "-1001",
            "trade_type": "CASH",
            "currency": "TWD",
            "account_id": "acct_A",
        },
        {
            "source_id": "syn",
            "physical_line": 2,
            "symbol": "X",
            "trade_date": "2024/1/2",
            "side": "SELL",
            "quantity": "100",
            "unit_price": "11",
            "gross_amount": "1100",
            "commission": "1",
            "tax": "3",
            "interest": "",
            "net_settlement": "1096",
            "trade_type": "CASH",
            "currency": "TWD",
            "account_id": "acct_A",
        },
    ]
    doc = ec.build_expected_c_document(
        case_id="GOLD-SYN-INT",
        source_sha256="a" * 64,
        source_path="synthetic/a.csv",
        source_format="capital_csv",
        applicable_spec=["SPEC.md §7"],
        rows=rows,
        opening_lots_policy="NONE_APPROVED",
        expected_source_sha256={"main": "a" * 64},
        actual_source_sha256={"main": "a" * 64},
        invalid_row_count=0,
    )
    assert doc["aggregates"]["interest"] == "UNKNOWN"
    assert doc["realized_and_open"]["status"] in {
        "PARTIAL_DUE_TO_UNKNOWN_INTEREST",
        "PARTIAL",
    }
    assert "interest_blank_rows" in doc["fields_not_computable"]
