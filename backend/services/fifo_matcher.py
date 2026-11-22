"""純函式 FIFO 配對（不直接寫入 DB）。"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from backend.domain.models import Allocation, LotRemaining, OpeningLot, ReconciliationIssue, Trade


@dataclass(frozen=True)
class MatchInputTrade:
    trade_id: str
    account_id: str
    symbol: str
    trade_date: date
    trade_time: str | None
    trade_sequence: int | None
    side: str
    trade_type: str
    currency: str
    quantity: int
    unit_price: Decimal
    # 僅作穩定排序 tie-breaker（來源列號），不代表已驗證成交先後
    source_order: int = 0


@dataclass
class MatchResult:
    allocations: list[Allocation]
    issues: list[ReconciliationIssue]
    unsold: list[LotRemaining]
    blocking: bool


def _group_key(account_id: str, symbol: str, currency: str, trade_type: str) -> tuple:
    return (account_id, symbol, currency, trade_type)


def detect_order_ambiguity(trades: list[MatchInputTrade]) -> list[ReconciliationIssue]:
    """CASH 同日不再因缺 time／seq 標 ORDER_AMBIGUITY。

    會計政策改為「開盤前庫存優先沖減 → 賣完再入庫當日買」；
    DAY_TRADE 本就不進此邏輯。保留函式與呼叫點以相容既有流程。
    """
    _ = trades
    return []


def _append_buy_lot(
    fifo: deque[LotRemaining],
    trade: MatchInputTrade,
    provenance: int,
) -> int:
    fifo.append(
        LotRemaining(
            buy_trade_id=trade.trade_id,
            opening_lot_id=None,
            available=trade.quantity,
            trade_date=trade.trade_date,
            unit_price=trade.unit_price,
            provenance_order=provenance,
        )
    )
    return provenance + 1


def _match_sell_against_lots(
    *,
    run_id: str,
    trade: MatchInputTrade,
    fifo: deque[LotRemaining],
    allocations: list[Allocation],
    issues: list[ReconciliationIssue],
    seq_counter: int,
    allow_future_buy: bool,
) -> int:
    sell_left = trade.quantity
    while sell_left > 0 and fifo:
        lot = fifo[0]
        if not allow_future_buy and lot.trade_date > trade.trade_date:
            break
        matched = min(lot.available, sell_left)
        seq_counter += 1
        allocations.append(
            Allocation(
                run_id=run_id,
                allocation_id=str(uuid.uuid4()),
                buy_trade_id=lot.buy_trade_id,
                opening_lot_id=lot.opening_lot_id,
                sell_trade_id=trade.trade_id,
                quantity=matched,
                sequence_no=seq_counter,
            )
        )
        lot.available -= matched
        sell_left -= matched
        if lot.available == 0:
            fifo.popleft()

    if sell_left > 0:
        issues.append(
            ReconciliationIssue(
                issue_code="INSUFFICIENT_PRIOR_BUYS",
                severity="blocking",
                trade_id=trade.trade_id,
                detail={
                    "unmatched_quantity": sell_left,
                    "symbol": trade.symbol,
                    "trade_date": trade.trade_date.isoformat(),
                },
            )
        )
    return seq_counter


def _cash_day_sort_key(trade: MatchInputTrade) -> tuple:
    """會計政策穩定鍵：非真實成交序；不得把 source_order／CSV 列號當真實時間。"""
    return (
        trade.trade_time or "",
        trade.trade_sequence if trade.trade_sequence is not None else 10**9,
        trade.source_order,
        trade.trade_id,
    )


def _run_cash_group(
    *,
    run_id: str,
    group_trades: list[MatchInputTrade],
    opening_lots: list[OpeningLot],
    allocations: list[Allocation],
    issues: list[ReconciliationIssue],
    unsold: list[LotRemaining],
    seq_counter: int,
) -> int:
    """CASH：按日先沖開盤前庫存（全部當日 SELL），再入庫當日 BUY。

    當日 BUY 不可供當日 SELL 使用；不足日產生 INSUFFICIENT_PRIOR_BUYS，
    不短路其他日期的配對迴圈。
    """
    fifo: deque[LotRemaining] = deque()
    provenance = 0
    for ol in sorted(opening_lots, key=lambda x: (x.buy_date, x.lot_id)):
        fifo.append(
            LotRemaining(
                buy_trade_id=None,
                opening_lot_id=ol.lot_id,
                available=ol.quantity,
                trade_date=ol.buy_date,
                unit_price=ol.unit_cost,
                provenance_order=provenance,
            )
        )
        provenance += 1

    by_day: dict[date, list[MatchInputTrade]] = defaultdict(list)
    for t in group_trades:
        by_day[t.trade_date].append(t)

    for day in sorted(by_day.keys()):
        day_trades = by_day[day]
        sells = sorted(
            [t for t in day_trades if t.side == "SELL"],
            key=_cash_day_sort_key,
        )
        buys = sorted(
            [t for t in day_trades if t.side == "BUY"],
            key=_cash_day_sort_key,
        )

        for sell in sells:
            seq_counter = _match_sell_against_lots(
                run_id=run_id,
                trade=sell,
                fifo=fifo,
                allocations=allocations,
                issues=issues,
                seq_counter=seq_counter,
                allow_future_buy=False,
            )

        for buy in buys:
            provenance = _append_buy_lot(fifo, buy, provenance)

    unsold.extend([lot for lot in fifo if lot.available > 0])
    return seq_counter


def _run_day_trade_group(
    *,
    run_id: str,
    group_trades: list[MatchInputTrade],
    allocations: list[Allocation],
    issues: list[ReconciliationIssue],
    unsold: list[LotRemaining],
    seq_counter: int,
) -> int:
    """同日無序現沖：當日 BUY 建 lot → 當日 SELL FIFO；lot 不跨日。"""
    by_day: dict[date, list[MatchInputTrade]] = defaultdict(list)
    for t in group_trades:
        by_day[t.trade_date].append(t)

    for day in sorted(by_day.keys()):
        day_trades = by_day[day]
        buys = sorted(
            [t for t in day_trades if t.side == "BUY"],
            key=lambda t: (t.source_order, t.trade_id),
        )
        sells = sorted(
            [t for t in day_trades if t.side == "SELL"],
            key=lambda t: (t.source_order, t.trade_id),
        )

        fifo: deque[LotRemaining] = deque()
        provenance = 0
        for buy in buys:
            provenance = _append_buy_lot(fifo, buy, provenance)

        for sell in sells:
            seq_counter = _match_sell_against_lots(
                run_id=run_id,
                trade=sell,
                fifo=fifo,
                allocations=allocations,
                issues=issues,
                seq_counter=seq_counter,
                allow_future_buy=True,  # 同日已先建 BUY lot
            )

        unsold.extend([lot for lot in fifo if lot.available > 0])

    return seq_counter


def run_fifo(
    run_id: str,
    trades: Iterable[MatchInputTrade],
    opening_lots: Iterable[OpeningLot] | None = None,
) -> MatchResult:
    trade_list = list(trades)
    ambiguity = detect_order_ambiguity(trade_list)

    groups: dict[tuple, list[MatchInputTrade]] = defaultdict(list)
    for t in trade_list:
        groups[_group_key(t.account_id, t.symbol, t.currency, t.trade_type)].append(t)

    lots_by_group: dict[tuple, list[OpeningLot]] = defaultdict(list)
    for lot in opening_lots or []:
        lots_by_group[_group_key(lot.account_id, lot.symbol, lot.currency, "CASH")].append(lot)

    allocations: list[Allocation] = []
    issues: list[ReconciliationIssue] = list(ambiguity)
    unsold: list[LotRemaining] = []
    seq_counter = 0

    for key, group_trades in sorted(groups.items(), key=lambda x: x[0]):
        trade_type = key[3]
        if trade_type == "DAY_TRADE":
            seq_counter = _run_day_trade_group(
                run_id=run_id,
                group_trades=group_trades,
                allocations=allocations,
                issues=issues,
                unsold=unsold,
                seq_counter=seq_counter,
            )
        else:
            seq_counter = _run_cash_group(
                run_id=run_id,
                group_trades=group_trades,
                opening_lots=lots_by_group.get(key, []),
                allocations=allocations,
                issues=issues,
                unsold=unsold,
                seq_counter=seq_counter,
            )

    blocking = any(i.severity == "blocking" for i in issues)
    return MatchResult(
        allocations=allocations,
        issues=issues,
        unsold=unsold,
        blocking=blocking,
    )


def input_fingerprint(trades: Iterable[MatchInputTrade], opening_lots: Iterable[OpeningLot]) -> str:
    payload = {
        "trades": [
            {
                "id": t.trade_id,
                "date": t.trade_date.isoformat(),
                "side": t.side,
                "type": t.trade_type,
                "qty": t.quantity,
                "price": str(t.unit_price),
                "symbol": t.symbol,
                "currency": t.currency,
                "seq": t.trade_sequence,
                "time": t.trade_time,
            }
            for t in sorted(trades, key=lambda x: x.trade_id)
        ],
        "lots": [
            {
                "id": o.lot_id,
                "date": o.buy_date.isoformat(),
                "qty": o.quantity,
                "cost": str(o.unit_cost),
                "symbol": o.symbol,
            }
            for o in sorted(opening_lots, key=lambda x: x.lot_id)
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def trade_from_domain(trade: Trade) -> MatchInputTrade:
    return MatchInputTrade(
        trade_id=trade.trade_id,
        account_id=trade.account_id,
        symbol=trade.symbol,
        trade_date=trade.trade_date,
        trade_time=trade.trade_time.isoformat() if trade.trade_time else None,
        trade_sequence=trade.trade_sequence,
        side=trade.side,
        trade_type=trade.trade_type,
        currency=trade.currency,
        quantity=trade.quantity,
        unit_price=trade.unit_price,
    )
