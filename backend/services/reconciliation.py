"""稽核與守恆檢查。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import (
    AllocationRun,
    FifoAllocation,
    OpeningLotRow,
    ReconciliationIssueRow,
    TradeRow,
)
from backend.domain.models import OpeningLot, txt_to_decimal
from backend.services.allocation_service import quantity_conservation


@dataclass
class AuditSummary:
    account_id: str
    run_id: str | None
    trade_count: int
    buy_count: int
    sell_count: int
    allocation_count: int
    issue_count: int
    blocking_issue_count: int
    conservation_ok: bool
    commission_total: str
    tax_total: str
    issues: list[dict]


def build_audit(session: Session, account_id: str, run_id: str | None = None) -> AuditSummary:
    trades = list(session.scalars(select(TradeRow).where(TradeRow.account_id == account_id)))
    run: AllocationRun | None
    if run_id:
        run = session.get(AllocationRun, run_id)
    else:
        run = session.scalar(
            select(AllocationRun)
            .where(AllocationRun.account_id == account_id)
            .order_by(AllocationRun.started_at_utc.desc())
            .limit(1)
        )

    allocations: list[FifoAllocation] = []
    issues: list[ReconciliationIssueRow] = []
    if run:
        allocations = list(
            session.scalars(select(FifoAllocation).where(FifoAllocation.run_id == run.id))
        )
        issues = list(
            session.scalars(
                select(ReconciliationIssueRow).where(ReconciliationIssueRow.run_id == run.id)
            )
        )

    opening_rows = list(
        session.scalars(
            select(OpeningLotRow).where(
                OpeningLotRow.account_id == account_id,
                OpeningLotRow.status == "approved",
            )
        )
    )
    openings = [
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
        for r in opening_rows
    ]
    cons = quantity_conservation(trades, allocations, opening_lots=openings)
    commission = sum((txt_to_decimal(t.commission_txt) for t in trades), Decimal(0))
    tax = sum((txt_to_decimal(t.tax_txt) for t in trades), Decimal(0))

    return AuditSummary(
        account_id=account_id,
        run_id=run.id if run else None,
        trade_count=len(trades),
        buy_count=sum(1 for t in trades if t.side == "BUY"),
        sell_count=sum(1 for t in trades if t.side == "SELL"),
        allocation_count=len(allocations),
        issue_count=len(issues),
        blocking_issue_count=sum(1 for i in issues if i.severity == "blocking"),
        conservation_ok=bool(cons["ok"]),
        commission_total=str(commission),
        tax_total=str(tax),
        issues=[
            {
                "id": i.id,
                "code": i.issue_code,
                "severity": i.severity,
                "trade_id": i.trade_id,
                "detail": json.loads(i.detail_json),
            }
            for i in issues
        ],
    )
