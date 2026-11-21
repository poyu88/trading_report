"""將 FIFO 配對投影為 A～W DetailRow 與配套 FIFO／未配對明細。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from backend.domain.models import DetailRow, LotRemaining
from backend.services.report_finance import (
    PARTIAL_MATCH_NOTE,
    compute_cost,
    compute_income,
    q2,
    split_gross,
    split_sell_gross_with_residual,
)

RATIO_PLACES = Decimal("0.0001")


@dataclass
class TradeView:
    trade_id: str
    symbol: str
    name: str | None
    trade_date: date
    side: str
    quantity: int
    unit_price: Decimal
    gross_amount: Decimal
    commission: Decimal
    tax: Decimal
    interest: Decimal
    broker_name: str
    trade_type: str = "CASH"


def _trade_type_label(trade_type: str) -> str:
    if trade_type == "DAY_TRADE":
        return "現沖"
    return "現股"


@dataclass
class OpeningLotView:
    lot_id: str
    symbol: str
    name: str | None
    buy_date: date
    quantity: int
    unit_cost: Decimal
    broker_name: str


@dataclass
class AllocationView:
    allocation_id: str
    buy_trade_id: str | None
    opening_lot_id: str | None
    sell_trade_id: str
    quantity: int
    sequence_no: int


@dataclass(frozen=True)
class FifoTraceRow:
    """配套「FIFO 配對及未配對明細」列。"""

    row_kind: str  # MATCHED | UNSOLD_BUY | UNMATCHED_SELL
    symbol: str
    name: str | None
    trade_type_label: str
    buy_date: date | None
    sell_date: date | None
    buy_trade_id: str | None
    sell_trade_id: str | None
    opening_lot_id: str | None
    allocation_id: str | None
    quantity: int
    unit_price: Decimal | None
    gross_amount: Decimal | None
    commission: Decimal | None
    tax: Decimal | None
    interest: Decimal | None
    cost: Decimal | None
    income: Decimal | None
    profit: Decimal | None
    broker: str
    note: str | None = None


def _split_gross(total: Decimal, pieces: list[int]) -> list[Decimal]:
    return split_gross(total, pieces)


def project_detail_rows(
    trades: Iterable[TradeView],
    allocations: Iterable[AllocationView],
    unsold: Iterable[LotRemaining],
    opening_lots: Iterable[OpeningLotView] | None = None,
) -> list[DetailRow]:
    trade_map = {t.trade_id: t for t in trades}
    lot_map = {o.lot_id: o for o in (opening_lots or [])}
    alloc_list = sorted(allocations, key=lambda a: a.sequence_no)

    buy_fragments: dict[str, list[tuple[str, int, AllocationView | None]]] = defaultdict(list)
    for a in alloc_list:
        if a.buy_trade_id:
            key = f"buy:{a.buy_trade_id}"
        else:
            key = f"lot:{a.opening_lot_id}"
        buy_fragments[key].append(("matched", a.quantity, a))

    for lot in unsold:
        if lot.buy_trade_id:
            key = f"buy:{lot.buy_trade_id}"
        else:
            key = f"lot:{lot.opening_lot_id}"
        buy_fragments[key].append(("unsold", lot.available, None))

    sell_first_alloc: dict[str, str] = {}
    for a in alloc_list:
        sell_first_alloc.setdefault(a.sell_trade_id, a.allocation_id)

    buy_gross_parts: dict[str, list[Decimal]] = {}
    for key, frags in buy_fragments.items():
        qtys = [q for _, q, _ in frags]
        if key.startswith("buy:"):
            trade = trade_map[key[4:]]
            buy_gross_parts[key] = _split_gross(trade.gross_amount, qtys)
        else:
            lot = lot_map[key[4:]]
            total = lot.unit_cost * Decimal(lot.quantity)
            buy_gross_parts[key] = _split_gross(total, qtys)

    sell_allocs: dict[str, list[AllocationView]] = defaultdict(list)
    for a in alloc_list:
        sell_allocs[a.sell_trade_id].append(a)

    sell_gross_by_alloc: dict[str, Decimal] = {}
    sell_has_residual: set[str] = set()
    for sell_id, alist in sell_allocs.items():
        trade = trade_map[sell_id]
        matched_parts, unmatched_gross, unmatched_qty = split_sell_gross_with_residual(
            trade.quantity,
            trade.gross_amount,
            [a.quantity for a in alist],
        )
        for a, part in zip(alist, matched_parts, strict=True):
            sell_gross_by_alloc[a.allocation_id] = part
        if unmatched_qty > 0:
            sell_has_residual.add(sell_id)
            _ = unmatched_gross  # 殘量價金由配套明細使用

    rows: list[DetailRow] = []
    buy_fee_used: set[str] = set()

    def sort_key(item: tuple[str, list]) -> tuple:
        key, _frags = item
        if key.startswith("buy:"):
            t = trade_map[key[4:]]
            return (t.symbol, t.trade_date, key)
        lot = lot_map[key[4:]]
        return (lot.symbol, lot.buy_date, key)

    for key, frags in sorted(buy_fragments.items(), key=sort_key):
        gross_parts = buy_gross_parts[key]
        for idx, (kind, qty, alloc) in enumerate(frags):
            buy_gross = gross_parts[idx]
            if key.startswith("buy:"):
                buy = trade_map[key[4:]]
                buy_date = buy.trade_date
                symbol = buy.symbol
                name = buy.name
                buy_price = buy.unit_price
                buy_trade_id = buy.trade_id
                opening_lot_id = None
                broker = buy.broker_name
                interest_src = buy.interest
                buy_commission_full = buy.commission
                type_label = _trade_type_label(buy.trade_type)
            else:
                lot = lot_map[key[4:]]
                buy_date = lot.buy_date
                symbol = lot.symbol
                name = lot.name
                buy_price = lot.unit_cost
                buy_trade_id = None
                opening_lot_id = lot.lot_id
                broker = lot.broker_name
                interest_src = Decimal(0)
                buy_commission_full = Decimal(0)
                type_label = "現股"

            fee_key = key
            if fee_key not in buy_fee_used:
                buy_commission = buy_commission_full
                buy_fee_used.add(fee_key)
            else:
                buy_commission = Decimal(0)

            cost = compute_cost(buy_gross, buy_commission)

            if kind == "unsold" or alloc is None:
                rows.append(
                    DetailRow(
                        buy_date=buy_date,
                        sell_date=None,
                        symbol=symbol,
                        name=name,
                        trade_type_label=type_label,
                        buy_price=buy_price,
                        buy_qty=qty,
                        buy_commission=buy_commission,
                        sell_price=None,
                        sell_qty=None,
                        sell_commission=None,
                        sell_tax=None,
                        interest=None,
                        margin_amount=None,
                        margin_annual_rate=None,
                        cost=cost,
                        income=None,
                        profit=None,
                        profit_rate=None,
                        actual_return_rate=None,
                        broker=broker,
                        market_correlation=None,
                        note=None,
                        buy_trade_id=buy_trade_id,
                        sell_trade_id=None,
                        opening_lot_id=opening_lot_id,
                        allocation_id=None,
                    )
                )
                continue

            sell = trade_map[alloc.sell_trade_id]
            sell_gross = sell_gross_by_alloc[alloc.allocation_id]
            is_first_sell = sell_first_alloc.get(sell.trade_id) == alloc.allocation_id
            sell_commission = sell.commission if is_first_sell else Decimal(0)
            sell_tax = sell.tax if is_first_sell else Decimal(0)
            sell_interest = sell.interest if is_first_sell else Decimal(0)

            # M 欄：第一賣出費用片段顯示賣出利息（含明確 0）；其餘空白
            if is_first_sell:
                interest: Decimal | None = sell_interest
            elif idx == 0 and interest_src:
                interest = interest_src
            else:
                interest = None

            income = compute_income(
                sell_gross,
                sell_commission=sell_commission,
                sell_tax=sell_tax,
                sell_interest=sell_interest,
            )
            profit = q2(income - cost)
            profit_rate = None
            if cost > 0:
                profit_rate = (profit / cost).quantize(RATIO_PLACES, rounding=ROUND_HALF_UP)

            note = PARTIAL_MATCH_NOTE if (is_first_sell and sell.trade_id in sell_has_residual) else None

            rows.append(
                DetailRow(
                    buy_date=buy_date,
                    sell_date=sell.trade_date,
                    symbol=symbol,
                    name=name or sell.name,
                    trade_type_label=type_label,
                    buy_price=buy_price,
                    buy_qty=qty,
                    buy_commission=buy_commission,
                    sell_price=sell.unit_price,
                    sell_qty=qty,
                    sell_commission=sell_commission,
                    sell_tax=sell_tax,
                    interest=interest,
                    margin_amount=None,
                    margin_annual_rate=None,
                    cost=cost,
                    income=income,
                    profit=profit,
                    profit_rate=profit_rate,
                    actual_return_rate=None,
                    broker=broker,
                    market_correlation=None,
                    note=note,
                    buy_trade_id=buy_trade_id,
                    sell_trade_id=sell.trade_id,
                    opening_lot_id=opening_lot_id,
                    allocation_id=alloc.allocation_id,
                )
            )

    rows.sort(
        key=lambda r: (
            r.symbol,
            r.buy_date,
            r.sell_date or date.max,
            r.allocation_id or "",
        )
    )
    return rows


def project_fifo_trace_rows(
    trades: Iterable[TradeView],
    allocations: Iterable[AllocationView],
    unsold: Iterable[LotRemaining],
    opening_lots: Iterable[OpeningLotView] | None = None,
) -> list[FifoTraceRow]:
    """產出 MATCHED／UNSOLD_BUY／UNMATCHED_SELL 配套列。"""
    trade_map = {t.trade_id: t for t in trades}
    alloc_list = sorted(allocations, key=lambda a: a.sequence_no)
    detail_rows = project_detail_rows(trades, allocations, unsold, opening_lots)

    sell_allocs: dict[str, list[AllocationView]] = defaultdict(list)
    for a in alloc_list:
        sell_allocs[a.sell_trade_id].append(a)

    sell_gross_by_alloc: dict[str, Decimal] = {}
    for sell_id, alist in sell_allocs.items():
        sell = trade_map[sell_id]
        matched_parts, _unmatched_gross, _unmatched_qty = split_sell_gross_with_residual(
            sell.quantity,
            sell.gross_amount,
            [a.quantity for a in alist],
        )
        for a, part in zip(alist, matched_parts, strict=True):
            sell_gross_by_alloc[a.allocation_id] = part

    trace: list[FifoTraceRow] = []
    for r in detail_rows:
        if r.allocation_id:
            trace.append(
                FifoTraceRow(
                    row_kind="MATCHED",
                    symbol=r.symbol,
                    name=r.name,
                    trade_type_label=r.trade_type_label,
                    buy_date=r.buy_date,
                    sell_date=r.sell_date,
                    buy_trade_id=r.buy_trade_id,
                    sell_trade_id=r.sell_trade_id,
                    opening_lot_id=r.opening_lot_id,
                    allocation_id=r.allocation_id,
                    quantity=r.buy_qty,
                    unit_price=r.sell_price,
                    gross_amount=sell_gross_by_alloc.get(r.allocation_id),
                    commission=r.sell_commission,
                    tax=r.sell_tax,
                    interest=r.interest,
                    cost=r.cost,
                    income=r.income,
                    profit=r.profit,
                    broker=r.broker,
                    note=r.note,
                )
            )
        else:
            buy_gross = q2(r.cost - r.buy_commission)
            trace.append(
                FifoTraceRow(
                    row_kind="UNSOLD_BUY",
                    symbol=r.symbol,
                    name=r.name,
                    trade_type_label=r.trade_type_label,
                    buy_date=r.buy_date,
                    sell_date=None,
                    buy_trade_id=r.buy_trade_id,
                    sell_trade_id=None,
                    opening_lot_id=r.opening_lot_id,
                    allocation_id=None,
                    quantity=r.buy_qty,
                    unit_price=r.buy_price,
                    gross_amount=buy_gross,
                    commission=r.buy_commission,
                    tax=None,
                    interest=None,
                    cost=r.cost,
                    income=None,
                    profit=None,
                    broker=r.broker,
                    note=None,
                )
            )

    for sell in sorted(
        [t for t in trade_map.values() if t.side == "SELL"],
        key=lambda t: (t.symbol, t.trade_date, t.trade_id),
    ):
        alist = sell_allocs.get(sell.trade_id, [])
        _matched_parts, unmatched_gross, unmatched_qty = split_sell_gross_with_residual(
            sell.quantity,
            sell.gross_amount,
            [a.quantity for a in alist],
        )
        if unmatched_qty <= 0 or unmatched_gross is None:
            continue
        fully_unmatched = len(alist) == 0
        commission = sell.commission if fully_unmatched else Decimal(0)
        tax = sell.tax if fully_unmatched else Decimal(0)
        interest = sell.interest if fully_unmatched else Decimal(0)
        note = (
            "完全未配對；費用見本列／資料庫原值，未落入主明細 A～W"
            if fully_unmatched
            else "未配對殘量；費用已落主明細第一已配對片段，本列不重複計費"
        )
        trace.append(
            FifoTraceRow(
                row_kind="UNMATCHED_SELL",
                symbol=sell.symbol,
                name=sell.name,
                trade_type_label=_trade_type_label(sell.trade_type),
                buy_date=None,
                sell_date=sell.trade_date,
                buy_trade_id=None,
                sell_trade_id=sell.trade_id,
                opening_lot_id=None,
                allocation_id=None,
                quantity=unmatched_qty,
                unit_price=sell.unit_price,
                gross_amount=unmatched_gross,
                commission=commission,
                tax=tax,
                interest=interest,
                cost=None,
                income=None,
                profit=None,
                broker=sell.broker_name,
                note=note,
            )
        )

    return trace
