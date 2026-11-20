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
    """同日同組同時有買與賣且無時間／序號時，列為阻擋性例外。"""
    issues: list[ReconciliationIssue] = []
    by_day: dict[tuple, list[MatchInputTrade]] = defaultdict(list)
    for t in trades:
        key = (_group_key(t.account_id, t.symbol, t.currency, t.trade_type), t.trade_date)
        by_day[key].append(t)

    for day_trades in by_day.values():
        sides = {t.side for t in day_trades}
        if not ({"BUY", "SELL"} <= sides):
            continue
        # 若所有交易都有可靠時間或序號，允許
        if all(t.trade_time or t.trade_sequence is not None for t in day_trades):
            continue
        # 進一步：若同日多筆買進單價不同且有賣出，無法判定哪個 lot 先被賣
        buys = [t for t in day_trades if t.side == "BUY"]
        sells = [t for t in day_trades if t.side == "SELL"]
        buy_prices = {t.unit_price for t in buys}
        affects = len(buys) > 1 and len(buy_prices) > 1 and len(sells) > 0
        # 同日買賣混合且缺少順序：一律視為影響結果
        if affects or (buys and sells):
            for t in day_trades:
                issues.append(
                    ReconciliationIssue(
                        issue_code="ORDER_AMBIGUITY",
                        severity="blocking",
                        trade_id=t.trade_id,
                        detail={
                            "trade_date": t.trade_date.isoformat(),
                            "symbol": t.symbol,
                            "reason": "同日買賣缺少可信時間或序號",
                        },
                    )
                )
    return issues


def run_fifo(
    run_id: str,
    trades: Iterable[MatchInputTrade],
    opening_lots: Iterable[OpeningLot] | None = None,
) -> MatchResult:
    trade_list = list(trades)
    ambiguity = detect_order_ambiguity(trade_list)
    ambiguous_trade_ids = {i.trade_id for i in ambiguity if i.trade_id}

    # 分組
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
        # 同日歧義組：不進行 FIFO，也不捏造未售（避免錯誤報表）
        if any(t.trade_id in ambiguous_trade_ids for t in group_trades):
            continue

        # 排序：日期 → sequence → id（無時間時僅用日期；同日歧義已攔截）
        ordered = sorted(
            group_trades,
            key=lambda t: (
                t.trade_date,
                t.trade_time or "",
                t.trade_sequence if t.trade_sequence is not None else 10**9,
                t.source_order,
                t.trade_id,
            ),
        )

        fifo: deque[LotRemaining] = deque()
        provenance = 0
        for ol in sorted(lots_by_group.get(key, []), key=lambda x: (x.buy_date, x.lot_id)):
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

        for trade in ordered:
            if trade.side == "BUY":
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
                provenance += 1
                continue

            sell_left = trade.quantity
            while sell_left > 0 and fifo:
                lot = fifo[0]
                # 不得配對未來買進
                if lot.trade_date > trade.trade_date:
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

        unsold.extend([lot for lot in fifo if lot.available > 0])

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
