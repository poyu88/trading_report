"""片段價金 TRUNC＋±1 容許差（合成測資）。

對照 SPEC §7.3、FEE-03/06、AUD-06；禁止比例分配與最後片段餘額法。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.domain.models import LotRemaining
from backend.reports.detail_projector import (
    AllocationView,
    TradeView,
    project_detail_rows,
    project_fifo_trace_rows,
)
from backend.reports.field_schema import HEADERS
from backend.services.report_finance import (
    AMOUNT_CONSERVATION_OUT_OF_TOLERANCE,
    allocate_trade_fragment_amounts,
)


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
    )


# --- 案 A：賣出 422＠64.8→27345；272+150；diff=0 ---


def test_case_a_sell_trunc_no_adjust_fees_on_first() -> None:
    """賣 422＠64.8 價金 27345 → 片段 17625／9720；費用全在第一；淨收入合計 27225。"""
    trades = [
        _tv("b1", side="BUY", qty=272, price="60", gross="16320", commission="0", d=date(2025, 1, 1)),
        _tv("b2", side="BUY", qty=150, price="61", gross="9150", commission="0", d=date(2025, 1, 2)),
        _tv(
            "s1",
            side="SELL",
            qty=422,
            price="64.8",
            gross="27345",
            commission="80",
            tax="40",
            interest="0",
            d=date(2025, 2, 1),
        ),
    ]
    allocs = [
        AllocationView("a1", "b1", None, "s1", 272, 1),
        AllocationView("a2", "b2", None, "s1", 150, 2),
    ]
    rows = project_detail_rows(trades, allocs, [])
    matched = sorted([r for r in rows if r.sell_trade_id == "s1"], key=lambda r: r.allocation_id or "")
    assert len(matched) == 2
    # income0 = 17625 - 120 = 17505；income1 = 9720
    assert matched[0].income == Decimal(17505)
    assert matched[1].income == Decimal(9720)
    assert matched[0].income + matched[1].income == Decimal(27225)
    assert matched[0].sell_commission == Decimal(80)
    assert matched[0].sell_tax == Decimal(40)
    assert matched[1].sell_commission == Decimal(0)
    assert matched[1].sell_tax == Decimal(0)

    result = allocate_trade_fragment_amounts(
        Decimal("64.8"), Decimal(27345), [272, 150]
    )
    assert result.amounts == [Decimal(17625), Decimal(9720)]
    assert result.difference == Decimal(0)
    assert not result.out_of_tolerance
    assert result.conservation_ok


# --- 案 B：買進 350＠94.6→33110；78+272；最後 +1 ---


def test_case_b_buy_trunc_adjust_last_plus_one() -> None:
    """買 350＠94.6 價金 33110 → 7378／25731→25732；成本 7425+25732。"""
    trades = [
        _tv(
            "b1",
            side="BUY",
            qty=350,
            price="94.6",
            gross="33110",
            commission="47",
            d=date(2025, 1, 1),
        ),
        _tv("s1", side="SELL", qty=78, price="100", gross="7800", commission="0", tax="0", d=date(2025, 2, 1)),
        _tv("s2", side="SELL", qty=272, price="100", gross="27200", commission="0", tax="0", d=date(2025, 2, 2)),
    ]
    allocs = [
        AllocationView("a1", "b1", None, "s1", 78, 1),
        AllocationView("a2", "b1", None, "s2", 272, 2),
    ]
    rows = project_detail_rows(trades, allocs, [])
    matched = sorted([r for r in rows if r.buy_trade_id == "b1"], key=lambda r: r.allocation_id or "")
    assert len(matched) == 2
    assert matched[0].cost == Decimal(7425)  # 7378 + 47
    assert matched[1].cost == Decimal(25732)
    assert matched[0].cost + matched[1].cost == Decimal(33157)

    result = allocate_trade_fragment_amounts(
        Decimal("94.6"), Decimal(33110), [78, 272]
    )
    assert result.truncated == [Decimal(7378), Decimal(25731)]
    assert result.difference == Decimal(1)
    assert result.amounts == [Decimal(7378), Decimal(25732)]
    assert result.adjustments == [Decimal(0), Decimal(1)]
    assert result.conservation_ok
    assert not result.out_of_tolerance


# --- ±1 容許 ---


def test_diff_plus_one_adjusts_last_fragment() -> None:
    result = allocate_trade_fragment_amounts(
        Decimal("94.6"), Decimal(33110), [78, 272]
    )
    assert result.difference == Decimal(1)
    assert sum(result.amounts, Decimal(0)) == Decimal(33110)


def test_diff_minus_one_adjusts_last_fragment() -> None:
    # TRUNC(10*1.1)=11, TRUNC(10*1.1)=11 → 22；gross 21 → diff=-1
    result = allocate_trade_fragment_amounts(
        Decimal("1.1"), Decimal(21), [10, 10]
    )
    assert result.difference == Decimal(-1)
    assert result.amounts == [Decimal(11), Decimal(10)]
    assert sum(result.amounts, Decimal(0)) == Decimal(21)
    assert result.conservation_ok


# --- ±2 超限 ---


def test_diff_plus_two_no_auto_adjust_emits_out_of_tolerance() -> None:
    # TRUNC(2*10.75)=21 ×2 = 42；gross 44 → diff=2
    result = allocate_trade_fragment_amounts(
        Decimal("10.75"), Decimal(44), [2, 2]
    )
    assert result.difference == Decimal(2)
    assert result.out_of_tolerance
    assert result.amounts == [Decimal(21), Decimal(21)]
    assert not result.conservation_ok
    assert result.exception_code == AMOUNT_CONSERVATION_OUT_OF_TOLERANCE
    detail = result.exception_detail()
    assert detail["trade_id"] is None or "difference" in detail
    assert Decimal(str(detail["original_gross"])) == Decimal(44)
    assert Decimal(str(detail["calculated_total"])) == Decimal(42)
    assert Decimal(str(detail["difference"])) == Decimal(2)


def test_diff_minus_two_no_auto_adjust() -> None:
    # TRUNC(2*10.75)=21 ×2 = 42；gross 40 → diff=-2
    result = allocate_trade_fragment_amounts(
        Decimal("10.75"), Decimal(40), [2, 2]
    )
    assert result.difference == Decimal(-2)
    assert result.out_of_tolerance
    assert result.amounts == result.truncated == [Decimal(21), Decimal(21)]
    assert not result.conservation_ok


def test_out_of_tolerance_projection_keeps_truncated_and_flags_issue() -> None:
    from backend.services.report_finance import collect_amount_conservation_issues

    trades = [
        _tv("b1", side="BUY", qty=4, price="10.75", gross="44", commission="0", d=date(2025, 1, 1)),
        _tv("s1", side="SELL", qty=2, price="12", gross="24", d=date(2025, 2, 1)),
        _tv("s2", side="SELL", qty=2, price="12", gross="24", d=date(2025, 2, 2)),
    ]
    allocs = [
        AllocationView("a1", "b1", None, "s1", 2, 1),
        AllocationView("a2", "b1", None, "s2", 2, 2),
    ]
    rows = project_detail_rows(trades, allocs, [])
    costs = sorted(
        [r.cost for r in rows if r.buy_trade_id == "b1"],
    )
    assert costs == [Decimal(21), Decimal(21)]
    issues = collect_amount_conservation_issues(trades, allocs, [])
    assert any(i["code"] == AMOUNT_CONSERVATION_OUT_OF_TOLERANCE for i in issues)
    assert all(
        not i.get("conservation_ok", True)
        for i in issues
        if i["code"] == AMOUNT_CONSERVATION_OUT_OF_TOLERANCE
    )


# --- 禁止餘額法／比例法 ---


def test_last_fragment_must_trunc_before_any_adjust() -> None:
    """最後片段須先 qty×price 再 TRUNC，禁止直接用 total−allocated。"""
    # 若餘額法：last = 27345 - TRUNC(272*64.8) = 27345-17625 = 9720（碰巧相同）
    # 用會暴露餘額法的案例：比例／餘額與雙截斷不同
    # 100＠1.5 → 150；片段 33+67
    # TRUNC(33*1.5)=49；TRUNC(67*1.5)=100；sum=149；diff=1 → last=101
    # 餘額法若先 TRUNC 第一再 last=150-49=101（相同）
    # 比例：33/100*150=49.5→49.50；last=100.50 — 與 TRUNC 路徑不同
    r2 = allocate_trade_fragment_amounts(Decimal("1.5"), Decimal(150), [33, 67])
    assert r2.truncated[0] == Decimal(49)
    assert r2.truncated[1] == Decimal(100)  # 必須是 TRUNC(67*1.5)，不是預先餘額
    assert r2.amounts[1] == Decimal(101)  # 再 +1


def test_forbids_proportional_allocation() -> None:
    total = Decimal(27345)
    qtys = [272, 150]
    total_qty = sum(qtys)
    proportional = [
        (total * Decimal(qtys[0]) / Decimal(total_qty)).quantize(Decimal("0.01")),
    ]
    # 第二段用餘額
    proportional.append(total - proportional[0])
    result = allocate_trade_fragment_amounts(Decimal("64.8"), total, qtys)
    assert result.amounts != proportional
    assert result.amounts == [Decimal(17625), Decimal(9720)]


# --- 未配對／未售納入守恆；原始欄位不變；A～W ---


def test_unmatched_and_unsold_included_in_trade_fragments() -> None:
    trades = [
        _tv("b1", side="BUY", qty=1000, price="10", gross="10000", commission="20", d=date(2025, 1, 1)),
        _tv(
            "s1",
            side="SELL",
            qty=1000,
            price="12",
            gross="12000",
            commission="5",
            tax="10",
            d=date(2025, 2, 1),
        ),
    ]
    allocs = [AllocationView("a1", "b1", None, "s1", 400, 1)]
    unsold = [LotRemaining("b1", None, 600, date(2025, 1, 1), Decimal(10), 0)]
    trace = project_fifo_trace_rows(trades, allocs, unsold)
    buy_frags = [r for r in trace if r.buy_trade_id == "b1"]
    assert sum(r.quantity for r in buy_frags) == 1000
    # 買進價金守恆：已配對 400＋未售 600（配套 MATCHED 列 gross 為賣出價金，故另算）
    buy_alloc = allocate_trade_fragment_amounts(Decimal(10), Decimal(10000), [400, 600])
    assert buy_alloc.conservation_ok
    assert sum(buy_alloc.amounts, Decimal(0)) == Decimal(10000)
    sell_frags = [r for r in trace if r.sell_trade_id == "s1"]
    assert sum(r.quantity for r in sell_frags) == 1000
    assert sum((r.gross_amount or Decimal(0) for r in sell_frags), Decimal(0)) == Decimal(12000)


def test_original_trade_fields_unchanged_after_projection() -> None:
    trades = [
        _tv("b1", side="BUY", qty=350, price="94.6", gross="33110", commission="47", d=date(2025, 1, 1)),
        _tv("s1", side="SELL", qty=78, price="100", gross="7800", d=date(2025, 2, 1)),
        _tv("s2", side="SELL", qty=272, price="100", gross="27200", d=date(2025, 2, 2)),
    ]
    before = [
        (t.trade_id, str(t.gross_amount), str(t.unit_price), t.quantity) for t in trades
    ]
    allocs = [
        AllocationView("a1", "b1", None, "s1", 78, 1),
        AllocationView("a2", "b1", None, "s2", 272, 2),
    ]
    project_detail_rows(trades, allocs, [])
    after = [
        (t.trade_id, str(t.gross_amount), str(t.unit_price), t.quantity) for t in trades
    ]
    assert before == after


def test_aw_contract_headers_and_fragment_qty_semantics() -> None:
    assert len(HEADERS) == 23
    trades = [
        _tv("b1", side="BUY", qty=272, price="60", gross="16320", d=date(2025, 1, 1)),
        _tv("b2", side="BUY", qty=150, price="61", gross="9150", d=date(2025, 1, 2)),
        _tv(
            "s1",
            side="SELL",
            qty=422,
            price="64.8",
            gross="27345",
            commission="80",
            tax="40",
            d=date(2025, 2, 1),
        ),
    ]
    allocs = [
        AllocationView("a1", "b1", None, "s1", 272, 1),
        AllocationView("a2", "b2", None, "s1", 150, 2),
    ]
    rows = project_detail_rows(trades, allocs, [])
    for r in rows:
        assert r.buy_price == trades[0].unit_price or r.buy_price in (
            Decimal(60),
            Decimal(61),
        )
        assert isinstance(r.buy_qty, int)
        if r.sell_qty is not None:
            assert r.sell_qty == r.buy_qty
            assert r.sell_price == Decimal("64.8")
        assert isinstance(r.cost, Decimal)
        if r.income is not None:
            assert isinstance(r.income, Decimal)
            assert r.profit == r.income - r.cost


def test_fifo_order_not_rewritten_by_display_sort_for_fees_and_tail() -> None:
    """費用落第一 FIFO 片段；±1 補差落最後 FIFO 片段（與 Excel 顯示排序無關）。"""
    trades = [
        _tv(
            "b1",
            side="BUY",
            qty=350,
            price="94.6",
            gross="33110",
            commission="47",
            d=date(2025, 3, 1),
        ),
        # 較早賣出日但 sequence 較後 → 顯示排序會把 s_early 列排前
        _tv("s_early", side="SELL", qty=272, price="100", gross="27200", d=date(2025, 1, 1)),
        _tv("s_late", side="SELL", qty=78, price="100", gross="7800", d=date(2025, 4, 1)),
    ]
    allocs = [
        AllocationView("a_first", "b1", None, "s_late", 78, 1),
        AllocationView("a_last", "b1", None, "s_early", 272, 2),
    ]
    rows = project_detail_rows(trades, allocs, [])
    by_alloc = {r.allocation_id: r for r in rows if r.allocation_id}
    assert by_alloc["a_first"].cost == Decimal(7425)  # 7378+47 費用在第一 FIFO
    assert by_alloc["a_last"].cost == Decimal(25732)  # 補差 +1 在最後 FIFO
    # 顯示順序：s_early 在前
    ordered = [r for r in rows if r.allocation_id]
    assert ordered[0].allocation_id == "a_last"
    assert ordered[1].allocation_id == "a_first"
