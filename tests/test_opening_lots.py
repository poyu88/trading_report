"""期初庫存參與 FIFO。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.domain.models import OpeningLot
from backend.services.fifo_matcher import MatchInputTrade, run_fifo


def test_opening_lot_covers_early_sell() -> None:
    lots = [
        OpeningLot(
            lot_id="ol1",
            account_id="acc",
            symbol="3260",
            currency="TWD",
            buy_date=date(2025, 1, 1),
            quantity=250,
            unit_cost=Decimal(100),
            approval_note="人工核准",
        )
    ]
    trades = [
        MatchInputTrade(
            "s1", "acc", "3260", date(2025, 10, 3), None, None, "SELL", "CASH", "TWD", 250, Decimal(172)
        )
    ]
    result = run_fifo("run", trades, lots)
    assert not result.blocking
    assert len(result.allocations) == 1
    assert result.allocations[0].opening_lot_id == "ol1"
    assert result.unsold == []
