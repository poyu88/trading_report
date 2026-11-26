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

from backend.config import ALGORITHM_VERSION, CASH_SAME_DAY_POLICY
from backend.domain.models import Allocation, LotRemaining, OpeningLot, ReconciliationIssue, Trade

MATCH_TYPE_STANDARD = "STANDARD_FIFO"
MATCH_TYPE_SAME_DAY = "SAME_DAY_RECONCILED"
MATCH_TYPE_DAY_TRADE = "DAY_TRADE_FIFO"


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


def _group_key(
    account_id: str, symbol: str, currency: str, trade_type: str
) -> tuple[str, str, str, str]:
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
    match_type: str,
    max_quantity: int | None = None,
    only_trade_date: date | None = None,
    record_issue: bool = True,
) -> tuple[int, int]:
    """對單一賣出沖減 lot。

    Args:
        run_id: 配對 run ID。
        trade: 賣出成交。
        fifo: 可消耗 lot 佇列（就地更新 ``available``）。
        allocations: 追加配對片段之輸出清單。
        issues: 追加／保留 reconciliation 例外。
        seq_counter: 目前 sequence_no。
        allow_future_buy: True 時允許 lot 日期晚於賣出（僅 DAY_TRADE 同日池）。
        match_type: 寫入 allocation 的稽核標籤。
        max_quantity: 若給定則只沖此數量（Pass2 殘量）。
        only_trade_date: 若給定則只消耗該日且來自 BUY 的 lot（禁止跨日／opening）。
        record_issue: False 時不足量不立刻寫 issue（Pass2 自行更新）。

    Returns:
        ``(seq_counter, remaining_unmatched)``。

    Side Effects:
        就地修改 ``fifo``／``allocations``／（可選）``issues``。

    Financial invariants:
        不造負庫存；``allocated_quantity > 0``；費用不在此函式落點。
    """
    sell_left = trade.quantity if max_quantity is None else max_quantity
    while sell_left > 0 and fifo:
        lot = fifo[0]
        if only_trade_date is not None:
            if lot.trade_date != only_trade_date or lot.buy_trade_id is None:
                break
        elif not allow_future_buy and lot.trade_date > trade.trade_date:
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
                match_type=match_type,
            )
        )
        lot.available -= matched
        sell_left -= matched
        if lot.available == 0:
            fifo.popleft()

    if sell_left > 0 and record_issue:
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
    return seq_counter, sell_left


def _cash_day_sort_key(trade: MatchInputTrade) -> tuple:
    """會計政策穩定鍵：非真實成交序；不得把 source_order／CSV 列號當真實時間。"""
    return (
        trade.trade_time or "",
        trade.trade_sequence if trade.trade_sequence is not None else 10**9,
        trade.source_order,
        trade.trade_id,
    )


def _pass2_same_day_reconcile(
    *,
    run_id: str,
    day: date,
    sells: list[MatchInputTrade],
    fifo: deque[LotRemaining],
    allocations: list[Allocation],
    issues: list[ReconciliationIssue],
    seq_counter: int,
) -> int:
    """Pass 2：以當日尚未消耗之 BUY lot 補沖當日未配 SELL。

    Args:
        run_id: 配對 run ID。
        day: 僅處理該日之 pending SELL。
        sells: 當日全部 SELL（用於 trade_id 對照）。
        fifo: Pass1 後剩餘 lot（含當日稍後建立之 BUY）。
        allocations: 追加 ``SAME_DAY_RECONCILED`` 片段。
        issues: 就地移除已解或更新殘量之 ``INSUFFICIENT_PRIOR_BUYS``。
        seq_counter: 目前 sequence_no。

    Returns:
        更新後的 ``seq_counter``。

    Side Effects:
        修改 ``fifo``／``allocations``／``issues``。

    Financial invariants:
        禁止跨日補沖；不得消耗 opening lot；部分補沖仍保留 blocking 殘量。
    """
    sell_by_id = {s.trade_id: s for s in sells}
    pending: list[tuple[MatchInputTrade, int, int]] = []
    for idx, issue in enumerate(issues):
        if issue.issue_code != "INSUFFICIENT_PRIOR_BUYS":
            continue
        if issue.trade_id not in sell_by_id:
            continue
        sell = sell_by_id[issue.trade_id]
        if sell.trade_date != day:
            continue
        unmatched = int(issue.detail.get("unmatched_quantity", 0))
        if unmatched > 0:
            pending.append((sell, unmatched, idx))

    # 依當日 SELL 穩定序處理
    pending.sort(key=lambda item: _cash_day_sort_key(item[0]))
    resolved_indexes: set[int] = set()
    updated: dict[int, int] = {}

    for sell, unmatched, idx in pending:
        seq_counter, remaining = _match_sell_against_lots(
            run_id=run_id,
            trade=sell,
            fifo=fifo,
            allocations=allocations,
            issues=issues,
            seq_counter=seq_counter,
            allow_future_buy=False,
            match_type=MATCH_TYPE_SAME_DAY,
            max_quantity=unmatched,
            only_trade_date=day,
            record_issue=False,
        )
        if remaining == 0:
            resolved_indexes.add(idx)
        elif remaining != unmatched:
            updated[idx] = remaining

    if resolved_indexes or updated:
        new_issues: list[ReconciliationIssue] = []
        for idx, issue in enumerate(issues):
            if idx in resolved_indexes:
                continue
            if idx in updated:
                detail = dict(issue.detail)
                detail["unmatched_quantity"] = updated[idx]
                new_issues.append(
                    ReconciliationIssue(
                        issue_code=issue.issue_code,
                        severity=issue.severity,
                        trade_id=issue.trade_id,
                        detail=detail,
                        batch_id=issue.batch_id,
                    )
                )
            else:
                new_issues.append(issue)
        issues[:] = new_issues

    return seq_counter


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
    """CASH Two-Pass：Pass1 開盤前庫存優先；Pass2 同日未用 BUY 補沖未配 SELL。

    Args:
        run_id: 配對 run ID。
        group_trades: 同一 ``account/symbol/currency`` 且 ``trade_type=CASH``。
        opening_lots: 已核准期初 lot（僅 CASH）。
        allocations: 輸出配對。
        issues: 輸出例外。
        unsold: 追加期末剩餘 lot。
        seq_counter: 目前 sequence_no。

    Returns:
        更新後的 ``seq_counter``。

    Side Effects:
        寫入 ``allocations``／``issues``／``unsold``。

    Financial invariants:
        Pass1 不穿插當日買解套；Pass2 不跨日、不改 DAY_TRADE；股數守恆。
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
            seq_counter, _ = _match_sell_against_lots(
                run_id=run_id,
                trade=sell,
                fifo=fifo,
                allocations=allocations,
                issues=issues,
                seq_counter=seq_counter,
                allow_future_buy=False,
                match_type=MATCH_TYPE_STANDARD,
            )

        for buy in buys:
            provenance = _append_buy_lot(fifo, buy, provenance)

        seq_counter = _pass2_same_day_reconcile(
            run_id=run_id,
            day=day,
            sells=sells,
            fifo=fifo,
            allocations=allocations,
            issues=issues,
            seq_counter=seq_counter,
        )

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
            seq_counter, _ = _match_sell_against_lots(
                run_id=run_id,
                trade=sell,
                fifo=fifo,
                allocations=allocations,
                issues=issues,
                seq_counter=seq_counter,
                allow_future_buy=True,  # 同日已先建 BUY lot
                match_type=MATCH_TYPE_DAY_TRADE,
            )

        unsold.extend([lot for lot in fifo if lot.available > 0])

    return seq_counter


def run_fifo(
    run_id: str,
    trades: Iterable[MatchInputTrade],
    opening_lots: Iterable[OpeningLot] | None = None,
) -> MatchResult:
    """對單一帳戶輸入執行 FIFO 配對（純函式，不寫 DB）。

    CASH：Two-Pass（開盤前庫存優先＋同日補沖銷）；DAY_TRADE：同日現沖分組。
    帳戶／標的／幣別／交易類型互不交叉配對。

    Args:
        run_id: 本次配對執行 ID（寫入 allocation 關聯）。
        trades: 已依帳戶篩選的成交輸入（含 source_order 穩定鍵）。
        opening_lots: 可選期初庫存；僅參與 CASH 組。

    Returns:
        ``MatchResult``（allocations／issues／unsold／blocking）。
    """
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
    """雜湊影響配對結果的輸入欄位（含排序穩定鍵與帳戶／幣別）。

    `source_order` 僅為決定性會計穩定鍵／來源列號 tie-breaker，
    **不得**解讀為已驗證的真實成交時間。
    """
    payload = {
        "algorithm_version": ALGORITHM_VERSION,
        "cash_same_day_policy": CASH_SAME_DAY_POLICY,
        "trades": [
            {
                "id": t.trade_id,
                "account_id": t.account_id,
                "date": t.trade_date.isoformat(),
                "side": t.side,
                "type": t.trade_type,
                "qty": t.quantity,
                "price": str(t.unit_price),
                "symbol": t.symbol,
                "currency": t.currency,
                "seq": t.trade_sequence,
                "time": t.trade_time,
                "source_order": t.source_order,
            }
            for t in sorted(trades, key=lambda x: x.trade_id)
        ],
        "lots": [
            {
                "id": o.lot_id,
                "account_id": o.account_id,
                "date": o.buy_date.isoformat(),
                "qty": o.quantity,
                "cost": str(o.unit_cost),
                "symbol": o.symbol,
                "currency": o.currency,
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
