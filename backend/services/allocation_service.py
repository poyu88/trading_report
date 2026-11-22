"""FIFO 配對入庫服務。"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import ALGORITHM_VERSION
from backend.db.models import (
    AllocationRun,
    FifoAllocation,
    OpeningLotRow,
    RawRow,
    ReconciliationIssueRow,
    TradeRow,
)
from backend.domain.models import OpeningLot, txt_to_decimal
from backend.services.fifo_matcher import MatchInputTrade, MatchResult, input_fingerprint, run_fifo


def _row_to_input(row: TradeRow, source_order: int = 0) -> MatchInputTrade:
    return MatchInputTrade(
        trade_id=row.id,
        account_id=row.account_id,
        symbol=row.symbol,
        trade_date=date.fromisoformat(row.trade_date),
        trade_time=row.trade_time,
        trade_sequence=row.trade_sequence,
        side=row.side,
        trade_type=row.trade_type,
        currency=row.currency,
        quantity=row.quantity,
        unit_price=txt_to_decimal(row.unit_price_txt),
        source_order=source_order,
    )


def _opening_lots(session: Session, account_id: str) -> list[OpeningLot]:
    rows = session.scalars(
        select(OpeningLotRow).where(
            OpeningLotRow.account_id == account_id,
            OpeningLotRow.status == "approved",
        )
    )
    return [
        OpeningLot(
            lot_id=r.id,
            account_id=r.account_id,
            symbol=r.symbol,
            currency=r.currency,
            buy_date=date.fromisoformat(r.buy_date),
            quantity=r.quantity,
            unit_cost=txt_to_decimal(r.unit_cost_txt),
            approval_note=r.approval_note,
            source_reference=r.source_reference,
        )
        for r in rows
    ]


def match_fifo_for_account(session: Session, account_id: str) -> tuple[AllocationRun, MatchResult]:
    """自 DB 載入帳戶成交與期初庫存，執行 FIFO 並寫入配對結果。

    Args:
        session: SQLAlchemy Session（呼叫端負責 commit／rollback）。
        account_id: 帳戶主鍵（非標籤）。

    Returns:
        ``(AllocationRun 列, MatchResult)``；blocking 時 run status 仍寫入供 DRAFT。
    """
    trade_rows = list(
        session.execute(
            select(TradeRow, RawRow.row_index)
            .join(RawRow, TradeRow.raw_row_id == RawRow.id)
            .where(TradeRow.account_id == account_id)
            .order_by(TradeRow.trade_date, RawRow.row_index, TradeRow.id)
        ).all()
    )
    inputs = [_row_to_input(r, source_order=idx) for r, idx in trade_rows]
    lots = _opening_lots(session, account_id)
    run_id = str(uuid.uuid4())
    fingerprint = input_fingerprint(inputs, lots)

    result = run_fifo(run_id, inputs, lots)
    status = "completed_with_issues" if result.blocking else "completed"
    if result.issues and not result.blocking:
        status = "completed_with_warnings"

    run = AllocationRun(
        id=run_id,
        algorithm_version=ALGORITHM_VERSION,
        input_fingerprint=fingerprint,
        started_at_utc=datetime.now(UTC),
        finished_at_utc=datetime.now(UTC),
        status=status,
        config_json=json.dumps(
            {
                "account_id": account_id,
                "cash_same_day_policy": "prior_inventory_first",
                "algorithm_version": ALGORITHM_VERSION,
            },
            ensure_ascii=False,
        ),
        account_id=account_id,
    )
    session.add(run)

    for alloc in result.allocations:
        session.add(
            FifoAllocation(
                id=alloc.allocation_id,
                run_id=run_id,
                buy_trade_id=alloc.buy_trade_id,
                opening_lot_id=alloc.opening_lot_id,
                sell_trade_id=alloc.sell_trade_id,
                allocated_quantity=alloc.quantity,
                sequence_no=alloc.sequence_no,
            )
        )

    for issue in result.issues:
        session.add(
            ReconciliationIssueRow(
                id=str(uuid.uuid4()),
                run_id=run_id,
                trade_id=issue.trade_id,
                issue_code=issue.issue_code,
                severity=issue.severity,
                detail_json=json.dumps(issue.detail, ensure_ascii=False),
            )
        )

    session.flush()
    return run, result


def quantity_conservation(
    trades: list[TradeRow],
    allocations: list[FifoAllocation],
    opening_lots: list[OpeningLot] | None = None,
) -> dict[str, Decimal | int | bool]:
    """核對買賣／期初庫存數量守恆（僅統計呼叫端傳入的當次 run allocations）。

    供給 = approved opening qty + BUY qty；
    守恆：supply = sold_from_buys + sold_from_openings + unsold_implied；
    賣出：sell_qty = allocated_sell + unmatched_implied。
    每筆 BUY／opening lot／SELL 不得超配。
    """
    lots = list(opening_lots or [])
    buy_qty = sum(t.quantity for t in trades if t.side == "BUY")
    sell_qty = sum(t.quantity for t in trades if t.side == "SELL")
    opening_qty = sum(o.quantity for o in lots)
    supply_qty = opening_qty + buy_qty
    allocated = sum(a.allocated_quantity for a in allocations)

    sold_by_buy: dict[str, int] = {}
    sold_by_opening: dict[str, int] = {}
    sold_by_sell: dict[str, int] = {}
    for a in allocations:
        if a.buy_trade_id:
            sold_by_buy[a.buy_trade_id] = sold_by_buy.get(a.buy_trade_id, 0) + a.allocated_quantity
        if a.opening_lot_id:
            sold_by_opening[a.opening_lot_id] = (
                sold_by_opening.get(a.opening_lot_id, 0) + a.allocated_quantity
            )
        sold_by_sell[a.sell_trade_id] = sold_by_sell.get(a.sell_trade_id, 0) + a.allocated_quantity

    sold_from_buys = sum(sold_by_buy.values())
    sold_from_openings = sum(sold_by_opening.values())
    ok = True

    for t in trades:
        if t.side == "BUY":
            if sold_by_buy.get(t.id, 0) > t.quantity:
                ok = False
        else:
            if sold_by_sell.get(t.id, 0) > t.quantity:
                ok = False

    lot_by_id = {o.lot_id: o for o in lots}
    for lot_id, sold in sold_by_opening.items():
        lot = lot_by_id.get(lot_id)
        if lot is None or sold > lot.quantity:
            ok = False

    # 配對不得超過供給或賣出；且來源拆分須等於 allocated
    if sold_from_buys + sold_from_openings != allocated:
        ok = False
    if allocated > supply_qty or allocated > sell_qty:
        ok = False

    return {
        "buy_qty": buy_qty,
        "sell_qty": sell_qty,
        "opening_qty": opening_qty,
        "supply_qty": supply_qty,
        "allocated_qty": allocated,
        "sold_from_buys": sold_from_buys,
        "sold_from_openings": sold_from_openings,
        "ok": ok,
    }
