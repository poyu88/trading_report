"""Two-Pass FIFO：同日補沖銷（Pass 2）RED／回歸。"""

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
    *,
    symbol: str = "2236",
    account: str = "acc1",
    seq: int | None = None,
    trade_time: str | None = None,
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
    *,
    symbol: str,
    account: str = "acc1",
) -> OpeningLot:
    return OpeningLot(
        lot_id=lot_id,
        account_id=account,
        symbol=symbol,
        currency="TWD",
        buy_date=date(2024, 12, 1),
        quantity=qty,
        unit_cost=Decimal(cost),
        approval_note="synthetic",
    )


def _qty_by_match_type(result) -> dict[str, int]:
    out: dict[str, int] = {}
    for a in result.allocations:
        out[a.match_type] = out.get(a.match_type, 0) + a.quantity
    return out


def test_c01_2236_two_pass_full_reconcile() -> None:
    """C01／2236：Pass1=3600 未配400；Pass2 SAME_DAY_RECONCILED=400；期末0。"""
    trades = [
        _t("b1", "2024-08-05", "BUY", 2000, "100", source_order=1),
        _t("b2", "2024-08-12", "BUY", 1000, "105", source_order=2),
        _t("s1", "2024-08-20", "SELL", 400, "110", source_order=3),
        _t("s2", "2024-08-20", "SELL", 1000, "111", source_order=4),
        _t("s3", "2024-08-26", "SELL", 1000, "112", source_order=5),
        _t("s4", "2024-08-28", "SELL", 1000, "113", source_order=6),
        _t("b3", "2024-08-28", "BUY", 1000, "114", source_order=7),
        _t("s5", "2024-09-02", "SELL", 579, "115", source_order=8),
        _t("s6", "2024-09-02", "SELL", 21, "116", source_order=9),
    ]
    result = run_fifo("2236", trades)
    assert not result.blocking
    assert sum(a.quantity for a in result.allocations) == 4000
    assert result.unsold == []
    assert not any(i.issue_code == "INSUFFICIENT_PRIOR_BUYS" for i in result.issues)

    by_type = _qty_by_match_type(result)
    assert by_type.get("STANDARD_FIFO", 0) == 3600
    assert by_type.get("SAME_DAY_RECONCILED", 0) == 400

    pass2 = [a for a in result.allocations if a.match_type == "SAME_DAY_RECONCILED"]
    assert len(pass2) == 1
    assert pass2[0].buy_trade_id == "b3"
    assert pass2[0].sell_trade_id == "s4"
    assert pass2[0].quantity == 400


def test_d02_next_day_buy_cannot_reconcile_prior_unmatched_sell() -> None:
    """D02：隔日買禁止補沖前一日未配賣出。"""
    result = run_fifo(
        "d02",
        [
            _t("s1", "2025-01-01", "SELL", 100, "10", symbol="AAA"),
            _t("b1", "2025-01-02", "BUY", 100, "9", symbol="AAA"),
        ],
    )
    assert result.blocking
    insuff = [i for i in result.issues if i.issue_code == "INSUFFICIENT_PRIOR_BUYS"]
    assert len(insuff) == 1
    assert insuff[0].trade_id == "s1"
    assert insuff[0].detail["unmatched_quantity"] == 100
    assert result.allocations == []
    assert any(u.buy_trade_id == "b1" and u.available == 100 for u in result.unsold)


def test_c11_pass2_does_not_reuse_consumed_lot() -> None:
    """C11：Pass2 不得重複消耗已被用盡的 lot；超額賣出用盡同日買後仍可 blocking。"""
    result = run_fifo(
        "c11",
        [
            _t("s1", "2025-03-20", "SELL", 800, "70", source_order=1, symbol="X"),
            _t("s2", "2025-03-20", "SELL", 700, "71", source_order=2, symbol="X"),
            _t("b1", "2025-03-20", "BUY", 500, "72", source_order=3, symbol="X"),
        ],
        [_ol("ol1", 1000, "60", symbol="X")],
    )
    # Pass1: 1000 from opening；未配 500；Pass2: b1 500 全用 → 配平
    assert not result.blocking
    assert sum(a.quantity for a in result.allocations) == 1500
    by_type = _qty_by_match_type(result)
    assert by_type["STANDARD_FIFO"] == 1000
    assert by_type["SAME_DAY_RECONCILED"] == 500
    assert sum(a.quantity for a in result.allocations if a.buy_trade_id == "b1") == 500
    assert result.unsold == []


def test_c12_pass2_does_not_cross_day_trade_pool() -> None:
    """C12：Pass2 不得跨 DAY_TRADE 池取 lot。"""
    result = run_fifo(
        "c12",
        [
            _t("cs1", "2025-03-20", "SELL", 1000, "70", trade_type="CASH", symbol="Y"),
            _t("db1", "2025-03-20", "BUY", 1000, "68", trade_type="DAY_TRADE", symbol="Y"),
            _t("ds1", "2025-03-20", "SELL", 1000, "69", trade_type="DAY_TRADE", symbol="Y"),
        ],
        [_ol("ol_y", 500, "60", symbol="Y")],
    )
    cash_pass2 = [
        a
        for a in result.allocations
        if a.sell_trade_id == "cs1" and a.match_type == "SAME_DAY_RECONCILED"
    ]
    assert cash_pass2 == []
    assert any(
        i.issue_code == "INSUFFICIENT_PRIOR_BUYS"
        and i.trade_id == "cs1"
        and i.detail["unmatched_quantity"] == 500
        for i in result.issues
    )
    dt = [a for a in result.allocations if a.sell_trade_id == "ds1"]
    assert len(dt) == 1
    assert dt[0].buy_trade_id == "db1"
    assert dt[0].match_type == "DAY_TRADE_FIFO"


def test_pass1_still_ignores_trade_time_interleave() -> None:
    """有 trade_time 時 Pass1 仍不穿插；Pass2 才補沖（仍為 CASH）。"""
    result = run_fifo(
        "time-pass2",
        [
            _t(
                "b1",
                "2025-03-20",
                "BUY",
                1000,
                "72",
                trade_time="09:00:00",
                seq=1,
                symbol="Z",
            ),
            _t(
                "s1",
                "2025-03-20",
                "SELL",
                1000,
                "70",
                trade_time="14:00:00",
                seq=2,
                symbol="Z",
            ),
        ],
    )
    assert not result.blocking
    assert len(result.allocations) == 1
    assert result.allocations[0].match_type == "SAME_DAY_RECONCILED"
    assert result.allocations[0].buy_trade_id == "b1"
    assert result.unsold == []
