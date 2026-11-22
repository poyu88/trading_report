"""FIFO-07／FIFO-08：同日無序現沖 FIFO，且不占用 CASH。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.reports.detail_projector import AllocationView, TradeView, project_detail_rows
from backend.services.fifo_matcher import MatchInputTrade, run_fifo


def _dt(
    tid: str,
    day: str,
    side: str,
    qty: int,
    price: str,
    *,
    trade_type: str = "DAY_TRADE",
    symbol: str = "3162",
    account: str = "acc1",
    source_order: int = 0,
) -> MatchInputTrade:
    return MatchInputTrade(
        trade_id=tid,
        account_id=account,
        symbol=symbol,
        trade_date=date.fromisoformat(day),
        trade_time=None,
        trade_sequence=None,
        side=side,
        trade_type=trade_type,
        currency="TWD",
        quantity=qty,
        unit_price=Decimal(price),
        source_order=source_order,
    )


def test_same_day_unordered_day_trade_sell_before_buy_matches() -> None:
    """檔內先賣後買、無時間序號：仍應同日 FIFO 配平。"""
    result = run_fifo(
        "run-dt",
        [
            _dt("ds1", "2025-02-25", "SELL", 1000, "52.4", source_order=1),
            _dt("db1", "2025-02-25", "BUY", 1000, "50.5", source_order=2),
        ],
    )
    assert not any(i.issue_code == "ORDER_AMBIGUITY" for i in result.issues)
    assert not result.blocking
    assert len(result.allocations) == 1
    assert result.allocations[0].quantity == 1000
    assert result.allocations[0].buy_trade_id == "db1"
    assert result.allocations[0].sell_trade_id == "ds1"
    assert result.unsold == []


def test_same_day_multi_day_trade_fifo_order() -> None:
    """同日兩筆現沖買、一筆賣：FIFO 先消耗第一筆買。"""
    result = run_fifo(
        "run-dt2",
        [
            _dt("db1", "2025-03-01", "BUY", 600, "10", source_order=1),
            _dt("db2", "2025-03-01", "BUY", 400, "11", source_order=2),
            _dt("ds1", "2025-03-01", "SELL", 700, "12", source_order=3),
        ],
    )
    assert not result.blocking
    assert sum(a.quantity for a in result.allocations) == 700
    by_buy = {a.buy_trade_id: a.quantity for a in result.allocations}
    assert by_buy["db1"] == 600
    assert by_buy["db2"] == 100
    assert len(result.unsold) == 1
    assert result.unsold[0].buy_trade_id == "db2"
    assert result.unsold[0].available == 300


def test_day_trade_does_not_consume_cash_lots() -> None:
    """跨日 CASH 買進不得被同日現沖賣出消耗。"""
    result = run_fifo(
        "run-iso",
        [
            _dt("cb1", "2025-01-01", "BUY", 1000, "40", trade_type="CASH"),
            _dt("ds1", "2025-02-25", "SELL", 1000, "52", trade_type="DAY_TRADE"),
            _dt("db1", "2025-02-25", "BUY", 1000, "50", trade_type="DAY_TRADE"),
        ],
    )
    # 現沖應自配；CASH 買進仍未售
    assert sum(a.quantity for a in result.allocations) == 1000
    assert all(a.buy_trade_id == "db1" for a in result.allocations)
    cash_unsold = [u for u in result.unsold if u.buy_trade_id == "cb1"]
    assert len(cash_unsold) == 1
    assert cash_unsold[0].available == 1000


def test_day_trade_does_not_match_across_days() -> None:
    """現沖 lot 不跨日：昨日現沖買不可配今日現沖賣。"""
    result = run_fifo(
        "run-xd",
        [
            _dt("db1", "2025-02-24", "BUY", 1000, "50"),
            _dt("ds1", "2025-02-25", "SELL", 1000, "52"),
        ],
    )
    assert result.allocations == []
    assert any(i.issue_code == "INSUFFICIENT_PRIOR_BUYS" for i in result.issues)
    assert any(u.buy_trade_id == "db1" and u.available == 1000 for u in result.unsold)


def test_day_trade_fee_once_on_split() -> None:
    """現沖一賣配兩買時，賣出手續費／稅只在第一片段。"""
    trades = [
        _dt("db1", "2025-03-01", "BUY", 600, "10", source_order=1),
        _dt("db2", "2025-03-01", "BUY", 400, "11", source_order=2),
        _dt("ds1", "2025-03-01", "SELL", 700, "12", source_order=3),
    ]
    result = run_fifo("run-fee", trades)
    trade_views = [
        TradeView(
            "db1", "3162", "精確", date(2025, 3, 1), "BUY", 600, Decimal(10), Decimal(6000),
            Decimal(20), Decimal(0), Decimal(0), "玉山",
        ),
        TradeView(
            "db2", "3162", "精確", date(2025, 3, 1), "BUY", 400, Decimal(11), Decimal(4400),
            Decimal(10), Decimal(0), Decimal(0), "玉山",
        ),
        TradeView(
            "ds1", "3162", "精確", date(2025, 3, 1), "SELL", 700, Decimal(12), Decimal(8400),
            Decimal(18), Decimal(36), Decimal(0), "玉山",
        ),
    ]
    alloc_views = [
        AllocationView(
            a.allocation_id, a.buy_trade_id, a.opening_lot_id, a.sell_trade_id, a.quantity, a.sequence_no
        )
        for a in result.allocations
    ]
    rows = project_detail_rows(trade_views, alloc_views, result.unsold)
    sell_fees = [(r.sell_commission, r.sell_tax) for r in rows if r.sell_trade_id == "ds1"]
    assert len(sell_fees) >= 2
    assert sum(c for c, _ in sell_fees) == Decimal(18)
    assert sum(t for _, t in sell_fees) == Decimal(36)
    # 費用只落在一個片段
    assert sum(1 for c, t in sell_fees if c != 0 or t != 0) == 1
