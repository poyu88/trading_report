"""FIFO 配對單元測試。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.services.fifo_matcher import MatchInputTrade, run_fifo


def _t(
    tid: str,
    day: str,
    side: str,
    qty: int,
    price: str,
    symbol: str = "1111",
    account: str = "acc1",
    seq: int | None = None,
    trade_time: str | None = None,
) -> MatchInputTrade:
    return MatchInputTrade(
        trade_id=tid,
        account_id=account,
        symbol=symbol,
        trade_date=date.fromisoformat(day),
        trade_time=trade_time,
        trade_sequence=seq,
        side=side,
        trade_type="CASH",
        currency="TWD",
        quantity=qty,
        unit_price=Decimal(price),
    )


def test_partial_sell() -> None:
    result = run_fifo(
        "run1",
        [_t("b1", "2025-01-01", "BUY", 1000, "10"), _t("s1", "2025-01-02", "SELL", 400, "12")],
    )
    assert not result.blocking
    assert len(result.allocations) == 1
    assert result.allocations[0].quantity == 400
    assert result.unsold[0].available == 600


def test_one_sell_two_buys() -> None:
    result = run_fifo(
        "run1",
        [
            _t("b1", "2025-01-01", "BUY", 1000, "10"),
            _t("b2", "2025-01-02", "BUY", 500, "12"),
            _t("s1", "2025-01-03", "SELL", 1200, "15"),
        ],
    )
    assert sum(a.quantity for a in result.allocations) == 1200
    assert result.unsold[0].available == 300
    by_buy = {a.buy_trade_id: a.quantity for a in result.allocations}
    assert by_buy["b1"] == 1000
    assert by_buy["b2"] == 200


def test_sell_before_buy_insufficient() -> None:
    result = run_fifo(
        "run1",
        [
            _t("s1", "2025-01-01", "SELL", 100, "10"),
            _t("b1", "2025-01-02", "BUY", 100, "9"),
        ],
    )
    assert result.blocking
    assert any(i.issue_code == "INSUFFICIENT_PRIOR_BUYS" for i in result.issues)
    assert result.allocations == []
    assert result.unsold[0].available == 100


def test_no_cross_symbol() -> None:
    result = run_fifo(
        "run1",
        [
            _t("b1", "2025-01-01", "BUY", 100, "10", symbol="A"),
            _t("s1", "2025-01-02", "SELL", 100, "12", symbol="B"),
        ],
    )
    assert any(i.issue_code == "INSUFFICIENT_PRIOR_BUYS" for i in result.issues)
    assert result.unsold[0].buy_trade_id == "b1"


def test_order_ambiguity_same_day() -> None:
    result = run_fifo(
        "run1",
        [
            _t("b1", "2025-01-01", "BUY", 100, "10"),
            _t("s1", "2025-01-01", "SELL", 50, "12"),
        ],
    )
    assert result.blocking
    assert any(i.issue_code == "ORDER_AMBIGUITY" for i in result.issues)
