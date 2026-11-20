"""將 FIFO 配對投影為 A～W DetailRow。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from backend.domain.models import DetailRow, LotRemaining

TWOPLACES = Decimal("0.01")
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


def _q2(value: Decimal) -> Decimal:
    return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _split_gross(total: Decimal, pieces: list[int]) -> list[Decimal]:
    """依股數拆價金，尾差歸最後片段，合計等於 total。"""
    if not pieces:
        return []
    total_qty = sum(pieces)
    if total_qty <= 0:
        return [Decimal(0)] * len(pieces)
    amounts: list[Decimal] = []
    allocated = Decimal(0)
    for i, qty in enumerate(pieces):
        if i == len(pieces) - 1:
            amounts.append(total - allocated)
        else:
            part = _q2(total * Decimal(qty) / Decimal(total_qty))
            amounts.append(part)
            allocated += part
    return amounts


def project_detail_rows(
    trades: Iterable[TradeView],
    allocations: Iterable[AllocationView],
    unsold: Iterable[LotRemaining],
    opening_lots: Iterable[OpeningLotView] | None = None,
) -> list[DetailRow]:
    trade_map = {t.trade_id: t for t in trades}
    lot_map = {o.lot_id: o for o in (opening_lots or [])}
    alloc_list = sorted(allocations, key=lambda a: a.sequence_no)

    # 每個買進來源的片段：先配對、後未售
    buy_fragments: dict[str, list[tuple[str, int, AllocationView | None]]] = defaultdict(list)
    # key = buy_trade_id or opening:lot_id
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

    # 賣出片段順序（費用落點）
    sell_first_alloc: dict[str, str] = {}
    for a in alloc_list:
        sell_first_alloc.setdefault(a.sell_trade_id, a.allocation_id)

    # 買進價金拆分（含未售）
    buy_gross_parts: dict[str, list[Decimal]] = {}
    buy_qty_parts: dict[str, list[int]] = {}
    for key, frags in buy_fragments.items():
        qtys = [q for _, q, _ in frags]
        buy_qty_parts[key] = qtys
        if key.startswith("buy:"):
            trade = trade_map[key[4:]]
            buy_gross_parts[key] = _split_gross(trade.gross_amount, qtys)
        else:
            lot = lot_map[key[4:]]
            total = lot.unit_cost * Decimal(lot.quantity)
            # 未售／配對依剩餘與配對量拆
            buy_gross_parts[key] = _split_gross(total, qtys)

    # 賣出價金依 allocation 順序拆
    sell_allocs: dict[str, list[AllocationView]] = defaultdict(list)
    for a in alloc_list:
        sell_allocs[a.sell_trade_id].append(a)
    sell_gross_by_alloc: dict[str, Decimal] = {}
    for sell_id, alist in sell_allocs.items():
        trade = trade_map[sell_id]
        parts = _split_gross(trade.gross_amount, [a.quantity for a in alist])
        for a, part in zip(alist, parts, strict=True):
            sell_gross_by_alloc[a.allocation_id] = part

    rows: list[DetailRow] = []
    buy_fee_used: set[str] = set()

    # 產出順序：依 buy key 的買進日、provenance、再依片段
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

            fee_key = key
            if fee_key not in buy_fee_used:
                buy_commission = buy_commission_full
                buy_fee_used.add(fee_key)
            else:
                buy_commission = Decimal(0)

            cost = _q2(buy_gross + buy_commission)

            if kind == "unsold" or alloc is None:
                rows.append(
                    DetailRow(
                        buy_date=buy_date,
                        sell_date=None,
                        symbol=symbol,
                        name=name,
                        trade_type_label="現股",
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
            interest = interest_src if (idx == 0 and interest_src) else (
                sell.interest if is_first_sell and sell.interest else None
            )
            if interest == 0:
                interest = Decimal(0) if is_first_sell else None

            income = _q2(sell_gross - sell_commission - sell_tax)
            profit = _q2(income - cost)
            profit_rate = None
            if cost > 0:
                profit_rate = (profit / cost).quantize(RATIO_PLACES, rounding=ROUND_HALF_UP)

            rows.append(
                DetailRow(
                    buy_date=buy_date,
                    sell_date=sell.trade_date,
                    symbol=symbol,
                    name=name or sell.name,
                    trade_type_label="現股",
                    buy_price=buy_price,
                    buy_qty=qty,
                    buy_commission=buy_commission,
                    sell_price=sell.unit_price,
                    sell_qty=qty,
                    sell_commission=sell_commission,
                    sell_tax=sell_tax,
                    interest=interest if interest is not None else None,
                    margin_amount=None,
                    margin_annual_rate=None,
                    cost=cost,
                    income=income,
                    profit=profit,
                    profit_rate=profit_rate,
                    actual_return_rate=None,
                    broker=broker,
                    market_correlation=None,
                    note=None,
                    buy_trade_id=buy_trade_id,
                    sell_trade_id=sell.trade_id,
                    opening_lot_id=opening_lot_id,
                    allocation_id=alloc.allocation_id,
                )
            )

    # 穩定排序
    rows.sort(
        key=lambda r: (
            r.symbol,
            r.buy_date,
            r.sell_date or date.max,
            r.allocation_id or "",
        )
    )
    return rows
