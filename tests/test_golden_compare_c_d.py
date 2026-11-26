"""CR-10A：獨立 C 層與實際 D 層輸出比對（合成契約；禁改 C 配合 D）。

SOURCE: SYNTHETIC_CONTRACT — 禁從 Excel 反推 C；禁改 C 配合 D。
"""

from __future__ import annotations

from decimal import Decimal

from backend.golden.compare_c_d import (
    allocation_line_finance_rows,
    build_actual_d_from_pipeline,
    compare_allocation_lines_to_trace_rows,
    compare_expected_c_to_actual_d,
    golden_finance_from_expected_c,
    trade_source_fingerprint,
)


def _sample_c() -> dict:
    return {
        "case_id": "GOLD-SYN-001",
        "validation_status": "INDEPENDENTLY_COMPUTED",
        "source_integrity": {"status": "PASS"},
        "aggregates": {
            "valid_trade_count": 2,
            "buy_trade_count": 1,
            "sell_trade_count": 1,
            "buy_quantity": "100",
            "sell_quantity": "100",
            "buy_gross_amount": "1000",
            "sell_gross_amount": "1100",
            "buy_commission": "1",
            "sell_commission": "1",
            "tax": "3",
            "interest": "0",
            "interest_known": True,
            "net_settlement": "95",
            "fee_landing_policy": "source_values_unsplit",
            "unknown_side_count": 0,
        },
        "fifo_expected": {
            "standard_fifo_allocated_qty": 100,
            "same_day_reconciled_qty": 0,
            "unmatched_sell_qty": 0,
            "unsold_buy_qty": 0,
            "allocation_count": 1,
            "blocking_insufficient_prior_buys": False,
        },
        "allocations": [
            {
                "sequence_no": 1,
                "match_type": "STANDARD_FIFO",
                "buy_trade_id": "src:L3",
                "sell_trade_id": "src:L4",
                "quantity": 100,
                "symbol": "2236",
                "currency": "TWD",
                "account_id": "acct",
            }
        ],
        "allocation_lines": [
            {
                "sequence_no": 1,
                "match_type": "STANDARD_FIFO",
                "buy_trade_id": "src:L3",
                "sell_trade_id": "src:L4",
                "quantity": 100,
                "buy_gross": "1000",
                "sell_gross": "1100",
                "buy_commission_applied": "1",
                "sell_commission_applied": "1",
                "sell_tax_applied": "3",
                "sell_interest_applied": "0",
                "cost": "1001",
                "income": "1096",
                "realized_pnl": "95",
                "gross_conservation_ok": True,
            }
        ],
        "realized_and_open": {
            "status": "COMPUTED",
            "matched_allocated_qty": 100,
            "realized_pnl": "95",
            "open_quantity": 0,
            "open_cost": "0",
            "unmatched_sell_qty": 0,
            "same_day_reconciled_qty": 0,
            "standard_fifo_allocated_qty": 100,
            "amount_conservation_ok": True,
        },
        "trade_fingerprints": [
            {
                "source_trade_id": "src:L3",
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
                "source_trade_id": "src:L4",
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
    }


def test_trade_source_fingerprint_stable() -> None:
    fp = trade_source_fingerprint(
        symbol="2236",
        trade_date="2024-08-05",
        side="BUY",
        quantity=100,
        unit_price="10",
        gross_amount="1000",
        commission="1",
        tax="0",
        interest="0",
    )
    assert fp == trade_source_fingerprint(
        symbol="2236",
        trade_date="2024-08-05",
        side="BUY",
        quantity=100,
        unit_price="10.0",
        gross_amount="1000.00",
        commission="1",
        tax="0",
        interest="0",
    )


def test_compare_pass_when_aggregates_and_fifo_match() -> None:
    c = _sample_c()
    actual = build_actual_d_from_pipeline(
        trade_count=2,
        buy_qty=100,
        sell_qty=100,
        buy_gross=Decimal(1000),
        sell_gross=Decimal(1100),
        buy_commission=Decimal(1),
        sell_commission=Decimal(1),
        tax=Decimal(3),
        interest=Decimal(0),
        cost=Decimal(1001),
        income=Decimal(1096),
        realized_pnl=Decimal(95),
        open_quantity=0,
        open_cost=Decimal(0),
        standard_fifo_qty=100,
        same_day_qty=0,
        unmatched_sell_qty=0,
        unsold_buy_qty=0,
        allocation_fingerprints=[
            {
                "match_type": "STANDARD_FIFO",
                "quantity": 100,
                "buy_fp": trade_source_fingerprint(
                    symbol="2236",
                    trade_date="2024-08-05",
                    side="BUY",
                    quantity=100,
                    unit_price="10",
                    gross_amount="1000",
                    commission="1",
                    tax="0",
                    interest="0",
                ),
                "sell_fp": trade_source_fingerprint(
                    symbol="2236",
                    trade_date="2024-08-08",
                    side="SELL",
                    quantity=100,
                    unit_price="11",
                    gross_amount="1100",
                    commission="1",
                    tax="3",
                    interest="0",
                ),
            }
        ],
        trade_fingerprints=[
            trade_source_fingerprint(**t)
            for t in (
                {
                    "symbol": x["symbol"],
                    "trade_date": x["trade_date"],
                    "side": x["side"],
                    "quantity": x["quantity"],
                    "unit_price": x["unit_price"],
                    "gross_amount": x["gross_amount"],
                    "commission": x["commission"],
                    "tax": x["tax"],
                    "interest": x["interest"],
                }
                for x in c["trade_fingerprints"]
            )
        ],
    )
    result = compare_expected_c_to_actual_d(c, actual)
    assert result["ok"] is True
    assert result["diffs"] == {}


def test_compare_fails_when_realized_pnl_differs() -> None:
    c = _sample_c()
    actual = build_actual_d_from_pipeline(
        trade_count=2,
        buy_qty=100,
        sell_qty=100,
        buy_gross=Decimal(1000),
        sell_gross=Decimal(1100),
        buy_commission=Decimal(1),
        sell_commission=Decimal(1),
        tax=Decimal(3),
        interest=Decimal(0),
        cost=Decimal(1001),
        income=Decimal(1096),
        realized_pnl=Decimal(96),  # off-by-one
        open_quantity=0,
        open_cost=Decimal(0),
        standard_fifo_qty=100,
        same_day_qty=0,
        unmatched_sell_qty=0,
        unsold_buy_qty=0,
        allocation_fingerprints=[],
        trade_fingerprints=[],
    )
    result = compare_expected_c_to_actual_d(c, actual, require_allocation_match=False)
    assert result["ok"] is False
    assert "realized_pnl" in result["diffs"]


def test_compare_does_not_mutate_expected_c() -> None:
    c = _sample_c()
    snapshot = str(c)
    actual = build_actual_d_from_pipeline(
        trade_count=0,
        buy_qty=0,
        sell_qty=0,
        buy_gross=Decimal(0),
        sell_gross=Decimal(0),
        buy_commission=Decimal(0),
        sell_commission=Decimal(0),
        tax=Decimal(0),
        interest=Decimal(0),
        cost=Decimal(0),
        income=Decimal(0),
        realized_pnl=Decimal(0),
        open_quantity=0,
        open_cost=Decimal(0),
        standard_fifo_qty=0,
        same_day_qty=0,
        unmatched_sell_qty=0,
        unsold_buy_qty=0,
        allocation_fingerprints=[],
        trade_fingerprints=[],
    )
    compare_expected_c_to_actual_d(c, actual, require_allocation_match=False)
    assert str(c) == snapshot


def test_golden_finance_from_expected_c_maps_verify_keys() -> None:
    g = golden_finance_from_expected_c(_sample_c())
    assert g["buy_qty"] == Decimal(100)
    assert g["sell_qty"] == Decimal(100)
    assert g["buy_commission"] == Decimal(1)
    assert g["sell_commission"] == Decimal(1)
    assert g["tax"] == Decimal(3)
    assert g["cost"] == Decimal(1001)
    assert g["income"] == Decimal(1096)
    assert g["expected_report_profit"] == Decimal(95)
    assert g["min_detail_rows"] == Decimal(1)
    assert g["per_row_costs"] == [Decimal(1001)]
    assert g["per_row_incomes"] == [Decimal(1096)]
    assert len(g["per_row_lines"]) == 1
    assert g["per_row_lines"][0]["match_type"] == "STANDARD_FIFO"


def test_compare_allocation_lines_to_trace_rows_by_fingerprint() -> None:
    c = _sample_c()
    buy_fp = trade_source_fingerprint(
        symbol="2236",
        trade_date="2024-08-05",
        side="BUY",
        quantity=100,
        unit_price="10",
        gross_amount="1000",
        commission="1",
        tax="0",
        interest="0",
    )
    sell_fp = trade_source_fingerprint(
        symbol="2236",
        trade_date="2024-08-08",
        side="SELL",
        quantity=100,
        unit_price="11",
        gross_amount="1100",
        commission="1",
        tax="3",
        interest="0",
    )
    trade_id_to_fp = {"db-buy": buy_fp, "db-sell": sell_fp}
    trace_rows = [
        {
            "row_kind": "MATCHED",
            "match_type": "STANDARD_FIFO",
            "quantity": 100,
            "buy_trade_id": "db-buy",
            "sell_trade_id": "db-sell",
            "cost": Decimal(1001),
            "income": Decimal(1096),
            "profit": Decimal(95),
            "commission": Decimal(1),
            "tax": Decimal(3),
            "interest": Decimal(0),
        }
    ]
    ok = compare_allocation_lines_to_trace_rows(
        c, trace_rows, trade_id_to_fp=trade_id_to_fp
    )
    assert ok["ok"] is True
    # 逐筆互抵：成本＋1／另一筆概念上以同列偏移 → diffs
    bad_rows = [
        {
            **trace_rows[0],
            "cost": Decimal(1002),
            "income": Decimal(1097),
            "profit": Decimal(95),
        }
    ]
    bad = compare_allocation_lines_to_trace_rows(
        c, bad_rows, trade_id_to_fp=trade_id_to_fp
    )
    assert bad["ok"] is False
    assert any("cost" in k or "income" in k for k in bad["diffs"])


def test_allocation_line_finance_rows_not_from_excel_order() -> None:
    rows = allocation_line_finance_rows(_sample_c())
    assert rows[0]["buy_fp"]
    assert rows[0]["sell_fp"]
    assert rows[0]["cost"] == Decimal(1001)
