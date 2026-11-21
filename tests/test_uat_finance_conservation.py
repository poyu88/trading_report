"""UAT-01～22：部分配對價金／收入含利息／未配對守恆（合成測資）。

對照 SPEC FEE-04/05、AUD-04/05、§7.2–7.3、§8.2.1–8.2.2。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

from backend.domain.models import LotRemaining
from backend.reports.detail_projector import (
    AllocationView,
    TradeView,
    project_detail_rows,
)
from backend.services.fifo_matcher import MatchInputTrade, run_fifo


def _tv(
    tid: str,
    *,
    side: str,
    qty: int,
    price: str,
    gross: str,
    commission: str = "0",
    tax: str = "0",
    interest: str = "0",
    symbol: str = "3162",
    d: date = date(2025, 3, 3),
    trade_type: str = "CASH",
) -> TradeView:
    return TradeView(
        trade_id=tid,
        symbol=symbol,
        name="測",
        trade_date=d,
        side=side,
        quantity=qty,
        unit_price=Decimal(price),
        gross_amount=Decimal(gross),
        commission=Decimal(commission),
        tax=Decimal(tax),
        interest=Decimal(interest),
        broker_name="玉山",
        trade_type=trade_type,
    )


def _partial_one_buy_one_sell() -> tuple[list[TradeView], list[AllocationView], list[LotRemaining]]:
    """買 1000、賣 2000 → 配 1000、未配 1000；價金 94000。"""
    trades = [
        _tv("b1", side="BUY", qty=1000, price="50", gross="50000", commission="20", d=date(2025, 2, 1)),
        _tv(
            "s1",
            side="SELL",
            qty=2000,
            price="47",
            gross="94000",
            commission="133",
            tax="282",
            interest="0",
            d=date(2025, 3, 3),
        ),
    ]
    allocs = [
        AllocationView("a1", "b1", None, "s1", 1000, 1),
    ]
    unsold: list[LotRemaining] = []
    return trades, allocs, unsold


def _partial_two_buys_residual() -> tuple[list[TradeView], list[AllocationView], list]:
    """買 500+500、賣 2000 → 配 1000、未配 1000（對照 58f27eb8 結構）。"""
    trades = [
        _tv("b1", side="BUY", qty=500, price="50", gross="25000", commission="10", d=date(2025, 2, 20)),
        _tv("b2", side="BUY", qty=500, price="51", gross="25500", commission="10", d=date(2025, 2, 25)),
        _tv(
            "s1",
            side="SELL",
            qty=2000,
            price="47",
            gross="94000",
            commission="133",
            tax="282",
            interest="5",
            d=date(2025, 3, 3),
        ),
    ]
    allocs = [
        AllocationView("a1", "b1", None, "s1", 500, 1),
        AllocationView("a2", "b2", None, "s1", 500, 2),
    ]
    return trades, allocs, []


# --- UAT-01～04：部分配對價金／股數／費用守恆 ---


def test_uat01_partial_match_matched_gross_is_proportional_not_full() -> None:
    trades, allocs, unsold = _partial_one_buy_one_sell()
    rows = project_detail_rows(trades, allocs, unsold)
    matched = [r for r in rows if r.sell_trade_id == "s1"]
    assert len(matched) == 1
    # 1000/2000 * 94000 = 47000；不得把 94000 全灌入
    assert matched[0].income is not None
    # income = 47000 - 133 - 282 - 0 = 46585
    assert matched[0].income == Decimal("46585.00")
    assert matched[0].sell_qty == 1000


def test_uat02_one_sell_two_buys_plus_residual_gross_conserved() -> None:
    trades, allocs, unsold = _partial_two_buys_residual()
    rows = project_detail_rows(trades, allocs, unsold)
    matched = [r for r in rows if r.sell_trade_id == "s1"]
    assert len(matched) == 2
    # 片段價金合計應為 47000，不是 94000
    # 由 income 反推：第一列扣費息，第二列不扣
    # sell_gross_1 + sell_gross_2 = 47000
    income0 = matched[0].income
    income1 = matched[1].income
    assert income0 is not None and income1 is not None
    # 第一片段費用：133+282+5=420；假設均分 23500+23500
    # income0 = 23500 - 420 = 23080；income1 = 23500
    sell_gross_total = (income0 + Decimal("133") + Decimal("282") + Decimal("5")) + income1
    assert sell_gross_total == Decimal("47000.00")


def test_uat03_matched_qty_equals_allocation_qty() -> None:
    trades, allocs, unsold = _partial_two_buys_residual()
    rows = project_detail_rows(trades, allocs, unsold)
    matched = sorted(
        [r for r in rows if r.sell_trade_id == "s1"],
        key=lambda r: r.allocation_id or "",
    )
    assert [r.sell_qty for r in matched] == [500, 500]
    assert [r.buy_qty for r in matched] == [500, 500]


def test_uat04_fees_once_on_partial_match_first_fragment_only() -> None:
    trades, allocs, unsold = _partial_two_buys_residual()
    rows = project_detail_rows(trades, allocs, unsold)
    matched = sorted(
        [r for r in rows if r.sell_trade_id == "s1"],
        key=lambda r: r.allocation_id or "",
    )
    assert matched[0].sell_commission == Decimal("133")
    assert matched[0].sell_tax == Decimal("282")
    assert matched[0].interest == Decimal("5")
    assert matched[1].sell_commission == Decimal("0")
    assert matched[1].sell_tax == Decimal("0")
    assert matched[1].interest in (None, Decimal("0"))


# --- UAT-05～10：成本／收入／利息／Decimal ---


def test_uat05_cost_is_buy_gross_plus_buy_commission() -> None:
    trades, allocs, unsold = _partial_one_buy_one_sell()
    rows = project_detail_rows(trades, allocs, unsold)
    matched = [r for r in rows if r.sell_trade_id == "s1"][0]
    # buy 1000 全配：buy_gross=50000 + commission 20
    assert matched.cost == Decimal("50020.00")


def test_uat06_income_deducts_commission_and_tax() -> None:
    trades = [
        _tv("b1", side="BUY", qty=1000, price="10", gross="10000", commission="20", d=date(2025, 1, 1)),
        _tv(
            "s1",
            side="SELL",
            qty=1000,
            price="15",
            gross="15000",
            commission="18",
            tax="36",
            interest="0",
            d=date(2025, 1, 2),
        ),
    ]
    allocs = [AllocationView("a1", "b1", None, "s1", 1000, 1)]
    rows = project_detail_rows(trades, allocs, [])
    m = [r for r in rows if r.sell_trade_id == "s1"][0]
    assert m.income == Decimal("14946.00")  # 15000-18-36-0


def test_uat07_income_deducts_nonzero_interest() -> None:
    trades = [
        _tv("b1", side="BUY", qty=1000, price="10", gross="10000", commission="0", d=date(2025, 1, 1)),
        _tv(
            "s1",
            side="SELL",
            qty=1000,
            price="15",
            gross="15000",
            commission="10",
            tax="20",
            interest="7.5",
            d=date(2025, 1, 2),
        ),
    ]
    allocs = [AllocationView("a1", "b1", None, "s1", 1000, 1)]
    rows = project_detail_rows(trades, allocs, [])
    m = [r for r in rows if r.sell_trade_id == "s1"][0]
    assert m.income == Decimal("14962.50")  # 15000-10-20-7.5
    assert m.interest == Decimal("7.5")


def test_uat08_explicit_zero_interest_is_accepted() -> None:
    trades, allocs, unsold = _partial_one_buy_one_sell()
    rows = project_detail_rows(trades, allocs, unsold)
    m = [r for r in rows if r.sell_trade_id == "s1"][0]
    assert m.interest == Decimal("0")


def test_uat09_profit_equals_income_minus_cost() -> None:
    trades, allocs, unsold = _partial_one_buy_one_sell()
    rows = project_detail_rows(trades, allocs, unsold)
    m = [r for r in rows if r.sell_trade_id == "s1"][0]
    assert m.profit == m.income - m.cost  # type: ignore[operator]


def test_uat10_amounts_are_decimal_not_float() -> None:
    trades, allocs, unsold = _partial_one_buy_one_sell()
    rows = project_detail_rows(trades, allocs, unsold)
    m = [r for r in rows if r.sell_trade_id == "s1"][0]
    assert isinstance(m.cost, Decimal)
    assert isinstance(m.income, Decimal)
    assert isinstance(m.profit, Decimal)
    assert not isinstance(m.income, float)


# --- UAT-11～12：未配對不得虛構；價金不重複 ---


def test_uat11_unmatched_sell_trace_has_no_fake_cost_or_profit() -> None:
    from backend.reports.detail_projector import project_fifo_trace_rows

    trades, allocs, unsold = _partial_one_buy_one_sell()
    trace = project_fifo_trace_rows(trades, allocs, unsold)
    unmatched = [r for r in trace if r.row_kind == "UNMATCHED_SELL"]
    assert len(unmatched) == 1
    assert unmatched[0].quantity == 1000
    assert unmatched[0].gross_amount == Decimal("47000.00")
    assert unmatched[0].cost is None
    assert unmatched[0].profit is None
    assert unmatched[0].sell_trade_id == "s1"


def test_uat12_full_gross_not_double_counted_across_matched_and_unmatched() -> None:
    from backend.reports.detail_projector import project_fifo_trace_rows

    trades, allocs, unsold = _partial_two_buys_residual()
    trace = project_fifo_trace_rows(trades, allocs, unsold)
    sell_frags = [r for r in trace if r.sell_trade_id == "s1" and r.gross_amount is not None]
    assert sum((r.gross_amount for r in sell_frags), Decimal(0)) == Decimal("94000")
    matched_gross = sum(
        (r.gross_amount for r in sell_frags if r.row_kind == "MATCHED"),
        Decimal(0),
    )
    unmatched_gross = sum(
        (r.gross_amount for r in sell_frags if r.row_kind == "UNMATCHED_SELL"),
        Decimal(0),
    )
    assert matched_gross == Decimal("47000.00")
    assert unmatched_gross == Decimal("47000.00")


# --- UAT-13～15：池隔離／現沖／重跑 ---


def test_uat13_cash_and_day_trade_pools_do_not_cross_for_finance() -> None:
    trades = [
        MatchInputTrade(
            "cb", "acc", "1111", date(2025, 1, 1), None, None, "BUY", "CASH", "TWD", 1000, Decimal("10")
        ),
        MatchInputTrade(
            "ds", "acc", "1111", date(2025, 1, 1), None, None, "SELL", "DAY_TRADE", "TWD", 1000, Decimal("12")
        ),
        MatchInputTrade(
            "db", "acc", "1111", date(2025, 1, 1), None, None, "BUY", "DAY_TRADE", "TWD", 1000, Decimal("11")
        ),
    ]
    result = run_fifo("run", trades)
    # DAY_TRADE 賣出不得吃 CASH 買進
    assert all(a.buy_trade_id != "cb" for a in result.allocations)
    assert any(a.buy_trade_id == "db" and a.sell_trade_id == "ds" for a in result.allocations)


def test_uat14_day_trade_sell_before_buy_same_day_matches() -> None:
    trades = [
        MatchInputTrade(
            "ds", "acc", "2222", date(2025, 5, 1), None, None, "SELL", "DAY_TRADE", "TWD", 500, Decimal("20")
        ),
        MatchInputTrade(
            "db", "acc", "2222", date(2025, 5, 1), None, None, "BUY", "DAY_TRADE", "TWD", 500, Decimal("19")
        ),
    ]
    result = run_fifo("run", trades)
    assert len(result.allocations) == 1
    assert result.allocations[0].quantity == 500
    assert not any(i.issue_code == "INSUFFICIENT_PRIOR_BUYS" for i in result.issues)


def test_uat15_fifo_rerun_does_not_duplicate_allocations() -> None:
    trades = [
        MatchInputTrade(
            "b1", "acc", "3333", date(2025, 1, 1), None, None, "BUY", "CASH", "TWD", 100, Decimal("10")
        ),
        MatchInputTrade(
            "s1", "acc", "3333", date(2025, 1, 2), None, None, "SELL", "CASH", "TWD", 100, Decimal("11")
        ),
    ]
    r1 = run_fifo("run1", trades)
    r2 = run_fifo("run2", trades)
    assert len(r1.allocations) == len(r2.allocations) == 1
    assert r1.allocations[0].quantity == r2.allocations[0].quantity == 100


# --- UAT-16～18：主明細無合計；損益語意 ---


def test_uat16_main_detail_has_no_total_row(tmp_path: Path) -> None:
    from backend.reports.detail_writer import write_detail_xlsx

    trades, allocs, unsold = _partial_one_buy_one_sell()
    rows = project_detail_rows(trades, allocs, unsold)
    path = write_detail_xlsx(rows, tmp_path)
    wb = load_workbook(path)
    ws = wb.active
    assert ws is not None
    for r in range(2, (ws.max_row or 1) + 1):
        for c in range(1, 24):
            val = ws.cell(r, c).value
            if isinstance(val, str):
                assert "合計" not in val and "總合" not in val and "小計" not in val


def test_uat17_matched_rows_have_computable_profit() -> None:
    trades, allocs, unsold = _partial_one_buy_one_sell()
    rows = project_detail_rows(trades, allocs, unsold)
    matched = [r for r in rows if r.allocation_id]
    assert matched
    assert all(r.profit is not None and r.income is not None for r in matched)


def test_uat18_unsold_buy_profit_unknown() -> None:
    trades = [
        _tv("b1", side="BUY", qty=1000, price="10", gross="10000", commission="20", d=date(2025, 1, 1)),
        _tv("s1", side="SELL", qty=400, price="12", gross="4800", commission="5", tax="10", d=date(2025, 1, 2)),
    ]
    allocs = [AllocationView("a1", "b1", None, "s1", 400, 1)]
    unsold = [
        LotRemaining("b1", None, 600, date(2025, 1, 1), Decimal("10"), 0),
    ]
    rows = project_detail_rows(trades, allocs, unsold)
    unsold_rows = [r for r in rows if r.sell_date is None]
    assert unsold_rows
    assert all(r.profit is None and r.income is None for r in unsold_rows)


# --- UAT-19～22：W 註記／配套報表／audit 守恆 ---


def test_uat19_partial_match_first_fragment_has_residual_note() -> None:
    trades, allocs, unsold = _partial_one_buy_one_sell()
    rows = project_detail_rows(trades, allocs, unsold)
    matched = [r for r in rows if r.sell_trade_id == "s1"]
    assert matched[0].note is not None
    assert "未配對殘量" in matched[0].note
    assert "費用全額落點" in matched[0].note
    assert "非完整原始交易損益" in matched[0].note


def test_uat20_companion_trace_workbook_has_unmatched_sell(tmp_path: Path) -> None:
    from backend.reports.detail_projector import project_fifo_trace_rows
    from backend.reports.fifo_trace_writer import write_fifo_trace_xlsx

    trades, allocs, unsold = _partial_one_buy_one_sell()
    trace = project_fifo_trace_rows(trades, allocs, unsold)
    path = write_fifo_trace_xlsx(trace, tmp_path)
    wb = load_workbook(path)
    ws = wb.active
    assert ws is not None
    kinds = [ws.cell(r, 1).value for r in range(2, (ws.max_row or 1) + 1)]
    assert "UNMATCHED_SELL" in kinds
    assert "MATCHED" in kinds


def test_uat21_enrich_issue_includes_gross_conservation_fields() -> None:
    from backend.services.report_finance import enrich_sell_issue_finance

    trades, allocs, _ = _partial_one_buy_one_sell()
    detail = enrich_sell_issue_finance(
        sell_trade=trades[1],
        allocations=[a for a in allocs if a.sell_trade_id == "s1"],
        base_detail={"unmatched_quantity": 1000, "symbol": "3162", "trade_date": "2025-03-03"},
    )
    assert detail["matched_quantity"] == 1000
    assert detail["unmatched_quantity"] == 1000
    assert Decimal(str(detail["matched_gross"])) == Decimal("47000.00")
    assert Decimal(str(detail["unmatched_gross"])) == Decimal("47000.00")
    assert "fee_placement" in detail


def test_uat22_sell_residual_plus_matched_equals_source_gross() -> None:
    """對照計畫：8927 結構 491+509、價金 27400。"""
    trades = [
        _tv(
            "b1",
            side="BUY",
            qty=491,
            price="30",
            gross="14730",
            commission="20",
            symbol="8927",
            d=date(2025, 5, 6),
        ),
        _tv(
            "s1",
            side="SELL",
            qty=1000,
            price="27.4",
            gross="27400",
            commission="39",
            tax="82",
            interest="0",
            symbol="8927",
            d=date(2025, 12, 3),
        ),
    ]
    allocs = [AllocationView("a1", "b1", None, "s1", 491, 1)]
    rows = project_detail_rows(trades, allocs, [])
    matched = [r for r in rows if r.sell_trade_id == "s1"][0]
    # TRUNC(491×27.4)=13453；殘量 TRUNC(509×27.4)=13946；diff=+1 → 殘量 13947
    # income = 13453 - 39 - 82 - 0 = 13332（禁止比例 13453.40 路徑）
    assert matched.income == Decimal("13332")
    from backend.reports.detail_projector import project_fifo_trace_rows

    trace = project_fifo_trace_rows(trades, allocs, [])
    frags = [r for r in trace if r.sell_trade_id == "s1"]
    assert sum((r.gross_amount or Decimal(0) for r in frags), Decimal(0)) == Decimal("27400")
    unmatched = [r for r in frags if r.row_kind == "UNMATCHED_SELL"][0]
    assert unmatched.quantity == 509
    assert unmatched.gross_amount == Decimal("13947")
