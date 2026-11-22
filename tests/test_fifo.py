"""FIFO 配對單元測試。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.domain.models import OpeningLot
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
    *,
    trade_type: str = "CASH",
    currency: str = "TWD",
    source_order: int = 0,
) -> MatchInputTrade:
    return MatchInputTrade(
        trade_id=tid,
        account_id=account,
        symbol=symbol,
        trade_date=date.fromisoformat(day),
        trade_time=trade_time,
        trade_sequence=seq,
        side=side,
        trade_type=trade_type,
        currency=currency,
        quantity=qty,
        unit_price=Decimal(price),
        source_order=source_order,
    )


def _ol(
    lot_id: str,
    qty: int,
    cost: str,
    buy_date: str = "2024-12-01",
    *,
    symbol: str = "1111",
    account: str = "acc1",
    currency: str = "TWD",
) -> OpeningLot:
    return OpeningLot(
        lot_id=lot_id,
        account_id=account,
        symbol=symbol,
        currency=currency,
        buy_date=date.fromisoformat(buy_date),
        quantity=qty,
        unit_cost=Decimal(cost),
        approval_note="synthetic",
    )


def _business_keys(result) -> list[tuple]:
    """可比對的配對業務鍵（不含 UUID allocation_id）。"""
    return sorted(
        (
            a.buy_trade_id,
            a.opening_lot_id,
            a.sell_trade_id,
            a.quantity,
            a.sequence_no,
        )
        for a in result.allocations
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
    """同日 CASH 買賣無 time/seq + 足夠期初庫存 → 不標 ORDER_AMBIGUITY；賣沖舊 lot。"""
    result = run_fifo(
        "run1",
        [
            _t("b1", "2025-01-01", "BUY", 100, "10"),
            _t("s1", "2025-01-01", "SELL", 50, "12"),
        ],
        [_ol("ol1", 100, "9", "2024-12-01")],
    )
    assert not any(i.issue_code == "ORDER_AMBIGUITY" for i in result.issues)
    assert not result.blocking
    assert len(result.allocations) == 1
    assert result.allocations[0].opening_lot_id == "ol1"
    assert result.allocations[0].quantity == 50
    assert result.allocations[0].sell_trade_id == "s1"
    # 剩餘：舊 lot 50 + 當日買 100
    by_src = {(u.opening_lot_id, u.buy_trade_id): u for u in result.unsold}
    assert by_src[("ol1", None)].available == 50
    assert by_src[(None, "b1")].available == 100
    assert by_src[(None, "b1")].unit_price == Decimal(10)


def test_cash_prior_inventory_case1_exact_cover() -> None:
    """Case1：opening 1000；同日 SELL+BUY 各 1000 → 通過；unsold=當日買價。"""
    result = run_fifo(
        "c1",
        [
            _t("s1", "2025-03-20", "SELL", 1000, "70"),
            _t("b1", "2025-03-20", "BUY", 1000, "72"),
        ],
        [_ol("ol1", 1000, "60")],
    )
    assert not result.blocking
    assert not any(i.issue_code == "ORDER_AMBIGUITY" for i in result.issues)
    assert len(result.allocations) == 1
    assert result.allocations[0].opening_lot_id == "ol1"
    assert result.allocations[0].quantity == 1000
    assert len(result.unsold) == 1
    assert result.unsold[0].buy_trade_id == "b1"
    assert result.unsold[0].available == 1000
    assert result.unsold[0].unit_price == Decimal(72)


def test_cash_prior_inventory_case2_partial_opening_remain() -> None:
    """Case2：opening 2000；SELL+BUY 各 1000 → 剩舊 1000 + 新 1000。"""
    result = run_fifo(
        "c2",
        [
            _t("s1", "2025-03-20", "SELL", 1000, "70"),
            _t("b1", "2025-03-20", "BUY", 1000, "72"),
        ],
        [_ol("ol1", 2000, "60")],
    )
    assert not result.blocking
    by_src = {(u.opening_lot_id, u.buy_trade_id): u.available for u in result.unsold}
    assert by_src[("ol1", None)] == 1000
    assert by_src[(None, "b1")] == 1000


def test_cash_prior_inventory_case3_insufficient_no_day_trade_escape() -> None:
    """Case3：opening 500；SELL+BUY 各 1000 → blocking，不足 500；不得當沖解套。"""
    result = run_fifo(
        "c3",
        [
            _t("s1", "2025-03-20", "SELL", 1000, "70"),
            _t("b1", "2025-03-20", "BUY", 1000, "72"),
        ],
        [_ol("ol1", 500, "60")],
    )
    assert result.blocking
    insuff = [i for i in result.issues if i.issue_code == "INSUFFICIENT_PRIOR_BUYS"]
    assert len(insuff) == 1
    assert insuff[0].detail["unmatched_quantity"] == 500
    assert not any(i.issue_code == "ORDER_AMBIGUITY" for i in result.issues)
    # 部分配對 500 來自 opening；當日 BUY 不得解套當日 SELL
    assert sum(a.quantity for a in result.allocations) == 500
    assert all(a.opening_lot_id == "ol1" for a in result.allocations)
    assert all(a.buy_trade_id is None for a in result.allocations)
    assert any(u.buy_trade_id == "b1" and u.available == 1000 for u in result.unsold)


def test_cash_prior_inventory_case4_zero_opening_cash_blocks() -> None:
    """Case4：opening 0；同日 BUY+SELL CASH → blocking，無自動 DAY_TRADE。"""
    result = run_fifo(
        "c4",
        [
            _t("b1", "2025-03-20", "BUY", 1000, "72"),
            _t("s1", "2025-03-20", "SELL", 1000, "70"),
        ],
    )
    assert result.blocking
    assert any(i.issue_code == "INSUFFICIENT_PRIOR_BUYS" for i in result.issues)
    assert result.allocations == []
    assert not any(i.issue_code == "ORDER_AMBIGUITY" for i in result.issues)
    assert any(u.buy_trade_id == "b1" and u.available == 1000 for u in result.unsold)


def test_cash_prior_inventory_case5_day_trade_still_matches() -> None:
    """Case5：opening 0；BUY+SELL DAY_TRADE → 同日配平。"""
    result = run_fifo(
        "c5",
        [
            _t("ds1", "2025-03-20", "SELL", 1000, "70", trade_type="DAY_TRADE"),
            _t("db1", "2025-03-20", "BUY", 1000, "68", trade_type="DAY_TRADE"),
        ],
    )
    assert not result.blocking
    assert not any(i.issue_code == "ORDER_AMBIGUITY" for i in result.issues)
    assert len(result.allocations) == 1
    assert result.allocations[0].buy_trade_id == "db1"
    assert result.allocations[0].sell_trade_id == "ds1"
    assert result.unsold == []


def test_cash_prior_inventory_case6_multi_sell_exact() -> None:
    """Case6：opening 1000；同日多筆 SELL 合計 1000 → FIFO 配平。"""
    result = run_fifo(
        "c6",
        [
            _t("s1", "2025-03-20", "SELL", 400, "70", source_order=1),
            _t("s2", "2025-03-20", "SELL", 600, "71", source_order=2),
            _t("b1", "2025-03-20", "BUY", 1000, "72", source_order=3),
        ],
        [_ol("ol1", 1000, "60")],
    )
    assert not result.blocking
    assert sum(a.quantity for a in result.allocations) == 1000
    assert all(a.opening_lot_id == "ol1" for a in result.allocations)
    assert len(result.unsold) == 1
    assert result.unsold[0].buy_trade_id == "b1"


def test_cash_prior_inventory_case7_multi_sell_overage() -> None:
    """Case7：opening 1000；多筆 SELL 合計 1500 → 超額 500 blocking。"""
    result = run_fifo(
        "c7",
        [
            _t("s1", "2025-03-20", "SELL", 800, "70", source_order=1),
            _t("s2", "2025-03-20", "SELL", 700, "71", source_order=2),
            _t("b1", "2025-03-20", "BUY", 1000, "72", source_order=3),
        ],
        [_ol("ol1", 1000, "60")],
    )
    assert result.blocking
    insuff = [i for i in result.issues if i.issue_code == "INSUFFICIENT_PRIOR_BUYS"]
    assert sum(i.detail["unmatched_quantity"] for i in insuff) == 500
    assert sum(a.quantity for a in result.allocations) == 1000
    assert any(u.buy_trade_id == "b1" and u.available == 1000 for u in result.unsold)


def test_cash_prior_inventory_case8_cash_and_day_trade_isolated() -> None:
    """Case8：CASH 與 DAY_TRADE 同日並存 → 兩 pool 隔離。"""
    result = run_fifo(
        "c8",
        [
            _t("cs1", "2025-03-20", "SELL", 1000, "70", trade_type="CASH"),
            _t("cb1", "2025-03-20", "BUY", 1000, "72", trade_type="CASH"),
            _t("ds1", "2025-03-20", "SELL", 500, "69", trade_type="DAY_TRADE"),
            _t("db1", "2025-03-20", "BUY", 500, "68", trade_type="DAY_TRADE"),
        ],
        [_ol("ol1", 1000, "60")],
    )
    assert not result.blocking
    cash_alloc = [a for a in result.allocations if a.sell_trade_id == "cs1"]
    dt_alloc = [a for a in result.allocations if a.sell_trade_id == "ds1"]
    assert len(cash_alloc) == 1
    assert cash_alloc[0].opening_lot_id == "ol1"
    assert len(dt_alloc) == 1
    assert dt_alloc[0].buy_trade_id == "db1"
    assert any(u.buy_trade_id == "cb1" and u.available == 1000 for u in result.unsold)


def test_cash_prior_inventory_case9_no_cross_group() -> None:
    """Case9：多帳戶／多股票／幣別 → 不跨組。"""
    result = run_fifo(
        "c9",
        [
            _t("s_a", "2025-03-20", "SELL", 100, "10", account="accA", symbol="AAA"),
            _t("b_a", "2025-03-20", "BUY", 100, "11", account="accA", symbol="AAA"),
            _t("s_b", "2025-03-20", "SELL", 100, "20", account="accB", symbol="BBB", currency="USD"),
            _t("b_b", "2025-03-20", "BUY", 100, "21", account="accB", symbol="BBB", currency="USD"),
        ],
        [
            _ol("ol_a", 100, "9", account="accA", symbol="AAA"),
            # accB 無 opening → 該組不足
        ],
    )
    a_alloc = [a for a in result.allocations if a.sell_trade_id == "s_a"]
    assert len(a_alloc) == 1
    assert a_alloc[0].opening_lot_id == "ol_a"
    assert not any(a.sell_trade_id == "s_b" for a in result.allocations)
    assert any(
        i.issue_code == "INSUFFICIENT_PRIOR_BUYS" and i.trade_id == "s_b" for i in result.issues
    )
    # 不得跨組：accA opening 不可被 accB 消耗
    assert all(a.opening_lot_id != "ol_a" or a.sell_trade_id == "s_a" for a in result.allocations)


def test_cash_prior_inventory_case10_deterministic() -> None:
    """Case10：同一輸入跑兩次 → allocation 業務鍵可重現。"""
    trades = [
        _t("s1", "2025-03-20", "SELL", 400, "70", source_order=1),
        _t("s2", "2025-03-20", "SELL", 600, "71", source_order=2),
        _t("b1", "2025-03-20", "BUY", 1000, "72", source_order=3),
    ]
    lots = [_ol("ol1", 1000, "60")]
    r1 = run_fifo("c10a", trades, lots)
    r2 = run_fifo("c10b", trades, lots)
    assert _business_keys(r1) == _business_keys(r2)
    assert not r1.blocking


def test_cash_prior_inventory_1589_synthetic() -> None:
    """1589 合成：2023-03-20 SELL@69.8 + BUY@72.8；無 time/seq；沖 opening。"""
    result = run_fifo(
        "1589",
        [
            _t("s1589", "2023-03-20", "SELL", 1000, "69.8", symbol="1589"),
            _t("b1589", "2023-03-20", "BUY", 1000, "72.8", symbol="1589"),
        ],
        [_ol("ol1589", 1000, "65", "2023-01-01", symbol="1589")],
    )
    assert not any(i.issue_code == "ORDER_AMBIGUITY" for i in result.issues)
    assert not result.blocking
    assert len(result.allocations) == 1
    assert result.allocations[0].opening_lot_id == "ol1589"
    assert result.allocations[0].sell_trade_id == "s1589"
    assert result.allocations[0].quantity == 1000
    assert len(result.unsold) == 1
    assert result.unsold[0].buy_trade_id == "b1589"
    assert result.unsold[0].available == 1000
    assert result.unsold[0].unit_price == Decimal("72.8")


def test_cash_same_day_ignores_trade_time_buy_before_sell() -> None:
    """即使 trade_time 顯示買先於賣，CASH 仍不得用當日 BUY 解套當日 SELL。"""
    result = run_fifo(
        "time-policy",
        [
            _t("b1", "2025-03-20", "BUY", 1000, "72", trade_time="09:00:00", seq=1),
            _t("s1", "2025-03-20", "SELL", 1000, "70", trade_time="14:00:00", seq=2),
        ],
    )
    assert result.blocking
    assert any(i.issue_code == "INSUFFICIENT_PRIOR_BUYS" for i in result.issues)
    assert not any(i.issue_code == "ORDER_AMBIGUITY" for i in result.issues)
    assert result.allocations == []
    assert any(u.buy_trade_id == "b1" and u.available == 1000 for u in result.unsold)
