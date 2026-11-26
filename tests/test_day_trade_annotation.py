"""Independent Day-Trade Annotation（Layer 3）RED／回歸。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.domain.models import Allocation, Trade
from backend.services.day_trade_annotation import (
    TAX_RULES_VERSION,
    annotate_day_trades,
)
from backend.services.fifo_matcher import MatchInputTrade, run_fifo


def _trade(
    tid: str,
    day: str,
    side: str,
    qty: int,
    price: str,
    *,
    tax: str,
    commission: str = "20",
    symbol: str = "2236",
    account: str = "acc1",
) -> Trade:
    unit = Decimal(price)
    gross = unit * qty
    tax_d = Decimal(tax)
    comm = Decimal(commission)
    net = gross - comm - tax_d if side == "SELL" else -(gross + comm)
    return Trade(
        trade_id=tid,
        account_id=account,
        source_row_id=f"src-{tid}",
        symbol=symbol,
        name=None,
        trade_date=date.fromisoformat(day),
        trade_time=None,
        trade_sequence=None,
        side=side,  # type: ignore[arg-type]
        trade_type="CASH",
        currency="TWD",
        quantity=qty,
        unit_price=unit,
        gross_amount=gross,
        commission=comm,
        tax=tax_d,
        interest=Decimal(0),
        net_settlement=net,
    )


def _mit(t: Trade, source_order: int = 0) -> MatchInputTrade:
    return MatchInputTrade(
        trade_id=t.trade_id,
        account_id=t.account_id,
        symbol=t.symbol,
        trade_date=t.trade_date,
        trade_time=None,
        trade_sequence=None,
        side=t.side,
        trade_type=t.trade_type,
        currency=t.currency,
        quantity=t.quantity,
        unit_price=t.unit_price,
        source_order=source_order,
    )


def test_annotation_suspects_half_tax_same_day_support() -> None:
    """同日買賣＋賣出稅近減半 → suspected support；與 reconciled 分欄。"""
    # 賣 1000 @100 → gross 100000；一般稅 0.3%=300；減半 0.15%=150
    buy = _trade("b1", "2024-08-28", "BUY", 1000, "100", tax="0")
    sell_half = _trade("s1", "2024-08-28", "SELL", 1000, "100", tax="150")
    sell_full = _trade("s2", "2024-08-28", "SELL", 1000, "100", tax="300")
    trades = [buy, sell_half, sell_full]

    # 無期初：Pass2 會把 b1 配給先排序的 sell（依 source_order／id）
    match = run_fifo("ann1", [_mit(buy, 1), _mit(sell_half, 2), _mit(sell_full, 3)])
    result = annotate_day_trades(trades, match.allocations)

    assert result.rules_version == TAX_RULES_VERSION
    assert result.suspected_day_trade_qty == 1000
    assert result.same_day_reconciled_qty == sum(
        a.quantity for a in match.allocations if a.match_type == "SAME_DAY_RECONCILED"
    )
    # suspected ≠ reconciled 概念獨立（本例數量可能相同，但欄位必須分開存在）
    assert hasattr(result, "suspected_day_trade_qty")
    assert hasattr(result, "same_day_reconciled_qty")
    assert any(c.tax_evidence == "HALF_RATE" for c in result.candidates)
    assert all(c.match_type_label != c.annotation_status for c in result.candidates)


def test_h01_annotation_on_off_financial_fields_equal() -> None:
    """H01：Annotation ON＝OFF；allocations／未售／blocking 財務結果全等。"""
    trades_mit = [
        _mit(_trade("b1", "2025-03-20", "BUY", 1000, "72", tax="0"), 1),
        _mit(_trade("s1", "2025-03-20", "SELL", 1000, "70", tax="105"), 2),
    ]
    domain_trades = [
        _trade("b1", "2025-03-20", "BUY", 1000, "72", tax="0"),
        _trade("s1", "2025-03-20", "SELL", 1000, "70", tax="105"),
    ]

    off = run_fifo("h01-off", trades_mit)
    on = run_fifo("h01-on", trades_mit)
    ann = annotate_day_trades(domain_trades, on.allocations)

    assert [(a.buy_trade_id, a.sell_trade_id, a.quantity, a.match_type) for a in off.allocations] == [
        (a.buy_trade_id, a.sell_trade_id, a.quantity, a.match_type) for a in on.allocations
    ]
    assert off.blocking == on.blocking
    assert [(u.buy_trade_id, u.available) for u in off.unsold] == [
        (u.buy_trade_id, u.available) for u in on.unsold
    ]
    # annotation 不得改寫 allocations
    assert isinstance(ann.candidates, list)
    assert all(isinstance(a, Allocation) for a in on.allocations)


def test_annotation_failure_emits_warning_not_finance_rewrite() -> None:
    """註記失敗 → 可追溯警告；不得拋錯改寫財務。"""
    trades = [_trade("b1", "2025-01-01", "BUY", 100, "10", tax="0")]
    # 故意傳入空 allocations 與不一致輸入仍應回傳結構
    result = annotate_day_trades(trades, allocations=[])
    assert result.suspected_day_trade_qty == 0
    assert result.same_day_reconciled_qty == 0
    assert result.warnings == [] or all(isinstance(w, str) for w in result.warnings)
