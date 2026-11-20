"""費用一次性落點。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.domain.models import LotRemaining
from backend.reports.detail_projector import (
    AllocationView,
    TradeView,
    project_detail_rows,
)
from backend.services.fifo_matcher import MatchInputTrade, run_fifo


def test_fee_once_on_split_fragments() -> None:
    trades = [
        MatchInputTrade(
            "b1", "acc", "1111", date(2025, 1, 1), None, None, "BUY", "CASH", "TWD", 1000, Decimal("10")
        ),
        MatchInputTrade(
            "b2", "acc", "1111", date(2025, 1, 2), None, None, "BUY", "CASH", "TWD", 500, Decimal("12")
        ),
        MatchInputTrade(
            "s1", "acc", "1111", date(2025, 1, 3), None, None, "SELL", "CASH", "TWD", 1200, Decimal("15")
        ),
    ]
    result = run_fifo("run", trades)
    trade_views = [
        TradeView("b1", "1111", "測一", date(2025, 1, 1), "BUY", 1000, Decimal("10"), Decimal("10000"), Decimal("20"), Decimal("0"), Decimal("0"), "券商"),
        TradeView("b2", "1111", "測一", date(2025, 1, 2), "BUY", 500, Decimal("12"), Decimal("6000"), Decimal("10"), Decimal("0"), Decimal("0"), "券商"),
        TradeView("s1", "1111", "測一", date(2025, 1, 3), "SELL", 1200, Decimal("15"), Decimal("18000"), Decimal("18"), Decimal("36"), Decimal("0"), "券商"),
    ]
    alloc_views = [
        AllocationView(a.allocation_id, a.buy_trade_id, a.opening_lot_id, a.sell_trade_id, a.quantity, a.sequence_no)
        for a in result.allocations
    ]
    rows = project_detail_rows(trade_views, alloc_views, result.unsold)

    buy_fees = [r.buy_commission for r in rows if r.buy_trade_id == "b1"]
    assert buy_fees[0] == Decimal("20")
    assert all(f == 0 for f in buy_fees[1:])

    buy2_fees = [r.buy_commission for r in rows if r.buy_trade_id == "b2"]
    # b2 第一片段（配對 200）帶 10，未售 300 為 0
    assert sum(buy2_fees) == Decimal("10")
    assert buy2_fees[0] == Decimal("10")

    sell_fees = [(r.sell_commission, r.sell_tax) for r in rows if r.sell_trade_id == "s1"]
    assert sell_fees[0] == (Decimal("18"), Decimal("36"))
    assert all(c == 0 and t == 0 for c, t in sell_fees[1:])
