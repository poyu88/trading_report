"""明細報表產生服務。"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from backend.config import REPORT_SCHEMA_VERSION
from backend.db.models import (
    Account,
    AllocationRun,
    FifoAllocation,
    OpeningLotRow,
    ReportRun,
    TradeRow,
)
from backend.domain.exceptions import BlockingExceptionError
from backend.domain.models import Allocation, LotRemaining, Trade, txt_to_decimal
from backend.reports.audit_writer import write_audit_files
from backend.reports.conservation_writer import write_conservation_csv
from backend.reports.detail_projector import (
    AllocationView,
    OpeningLotView,
    TradeView,
    project_detail_rows,
    project_fifo_trace_rows,
)
from backend.reports.detail_writer import write_detail_xlsx
from backend.reports.fifo_trace_writer import write_fifo_trace_xlsx
from backend.services.day_trade_annotation import annotate_day_trades, annotation_to_audit_dict
from backend.services.reconciliation import build_audit
from backend.services.report_finance import (
    collect_amount_conservation_issues,
    enrich_sell_issue_finance,
)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def generate_detail_report(
    session: Session,
    account_id: str,
    output_dir: Path,
    *,
    allow_partial: bool = False,
    run_id: str | None = None,
    include_day_trade_annotation: bool = True,
) -> tuple[Path, Path, Path]:
    """產生明細 Excel、audit.json 與 exceptions.csv。

    Args:
        session: DB session。
        account_id: 帳戶 ID。
        output_dir: 報表輸出目錄。
        allow_partial: True 時 blocking 改產 DRAFT。
        run_id: 指定 allocation run；預設取最新。
        include_day_trade_annotation: 是否附掛 Layer 3 annotation（預設 True）。

    Returns:
        ``(xlsx_path, audit_path, exceptions_path)``。

    Side Effects:
        寫入 ``output_dir`` 檔案並新增 ``ReportRun`` 列。

    Financial invariants:
        Annotation 失敗僅寫入 audit warnings，不中斷已產出之 detail／trace／conservation。
    """
    account = session.scalar(
        select(Account)
        .options(joinedload(Account.broker))
        .where(Account.id == account_id)
    )
    if not account:
        raise ValueError(f"找不到帳戶：{account_id}")

    if run_id:
        run = session.get(AllocationRun, run_id)
    else:
        run = session.scalar(
            select(AllocationRun)
            .where(AllocationRun.account_id == account_id)
            .order_by(AllocationRun.started_at_utc.desc())
            .limit(1)
        )
    if not run:
        raise ValueError("尚無 FIFO 配對結果，請先執行 match fifo")

    audit = build_audit(session, account_id, run.id)
    if audit.blocking_issue_count > 0 and not allow_partial:
        raise BlockingExceptionError(
            f"存在 {audit.blocking_issue_count} 筆阻擋性例外；"
            "請處理後重跑，或使用 --allow-partial 產生 DRAFT"
        )

    trades = list(session.scalars(select(TradeRow).where(TradeRow.account_id == account_id)))
    allocations = list(
        session.scalars(select(FifoAllocation).where(FifoAllocation.run_id == run.id))
    )
    opening_rows = list(
        session.scalars(
            select(OpeningLotRow).where(
                OpeningLotRow.account_id == account_id,
                OpeningLotRow.status == "approved",
            )
        )
    )

    broker_name = account.broker.name if account.broker else ""
    trade_views = [
        TradeView(
            trade_id=t.id,
            symbol=t.symbol,
            name=t.name,
            trade_date=date.fromisoformat(t.trade_date),
            side=t.side,
            quantity=t.quantity,
            unit_price=txt_to_decimal(t.unit_price_txt),
            gross_amount=txt_to_decimal(t.gross_amount_txt),
            commission=txt_to_decimal(t.commission_txt),
            tax=txt_to_decimal(t.tax_txt),
            interest=txt_to_decimal(t.interest_txt),
            broker_name=broker_name,
            trade_type=t.trade_type,
        )
        for t in trades
    ]
    alloc_views = [
        AllocationView(
            allocation_id=a.id,
            buy_trade_id=a.buy_trade_id,
            opening_lot_id=a.opening_lot_id,
            sell_trade_id=a.sell_trade_id,
            quantity=a.allocated_quantity,
            sequence_no=a.sequence_no,
            match_type=getattr(a, "match_type", None) or "STANDARD_FIFO",
        )
        for a in allocations
    ]
    lot_views = [
        OpeningLotView(
            lot_id=o.id,
            symbol=o.symbol,
            name=None,
            buy_date=date.fromisoformat(o.buy_date),
            quantity=o.quantity,
            unit_cost=txt_to_decimal(o.unit_cost_txt),
            broker_name=broker_name,
        )
        for o in opening_rows
    ]

    unsold = _compute_unsold(trade_views, alloc_views, lot_views)

    rows = project_detail_rows(trade_views, alloc_views, unsold, lot_views)
    trace_rows = project_fifo_trace_rows(trade_views, alloc_views, unsold, lot_views)
    draft = allow_partial and audit.blocking_issue_count > 0
    xlsx_path = write_detail_xlsx(rows, output_dir, draft=draft)
    trace_path = write_fifo_trace_xlsx(trace_rows, output_dir)
    conservation_path = write_conservation_csv(
        trade_views, alloc_views, trace_rows, output_dir
    )

    trade_by_id = {t.trade_id: t for t in trade_views}
    enriched_issues: list[dict] = []
    for issue in audit.issues:
        detail = dict(issue.get("detail") or {})
        tid = issue.get("trade_id")
        if issue.get("code") == "INSUFFICIENT_PRIOR_BUYS" and tid and tid in trade_by_id:
            detail = enrich_sell_issue_finance(
                sell_trade=trade_by_id[tid],
                allocations=[a for a in alloc_views if a.sell_trade_id == tid],
                base_detail=detail,
            )
        enriched_issues.append({**issue, "detail": detail})

    amount_issues = collect_amount_conservation_issues(trade_views, alloc_views, unsold)
    enriched_issues.extend(amount_issues)
    audit.issues = enriched_issues
    audit.issue_count = len(enriched_issues)
    if amount_issues:
        # 超容許差不得讓 conservation_ok 維持 true
        audit.conservation_ok = False

    annotation_extra: dict = {}
    if include_day_trade_annotation:
        # CR-04：專用資料準備／分析／serialization 全包於例外邊界；OFF 時不執行
        try:
            domain_trades = [
                Trade(
                    trade_id=t.id,
                    account_id=t.account_id,
                    source_row_id=t.raw_row_id,
                    symbol=t.symbol,
                    name=t.name,
                    trade_date=date.fromisoformat(t.trade_date),
                    trade_time=None,
                    trade_sequence=t.trade_sequence,
                    side=t.side,  # type: ignore[arg-type]
                    trade_type=t.trade_type,  # type: ignore[arg-type]
                    currency=t.currency,
                    quantity=t.quantity,
                    unit_price=txt_to_decimal(t.unit_price_txt),
                    gross_amount=txt_to_decimal(t.gross_amount_txt),
                    commission=txt_to_decimal(t.commission_txt),
                    tax=txt_to_decimal(t.tax_txt),
                    interest=txt_to_decimal(t.interest_txt),
                    net_settlement=(
                        txt_to_decimal(t.net_settlement_txt)
                        if t.net_settlement_txt
                        else None
                    ),
                )
                for t in trades
            ]
            domain_allocs = [
                Allocation(
                    run_id=run.id,
                    allocation_id=a.id,
                    buy_trade_id=a.buy_trade_id,
                    opening_lot_id=a.opening_lot_id,
                    sell_trade_id=a.sell_trade_id,
                    quantity=a.allocated_quantity,
                    sequence_no=a.sequence_no,
                    match_type=getattr(a, "match_type", None) or "STANDARD_FIFO",
                )
                for a in allocations
            ]
            annotation_extra = annotation_to_audit_dict(
                annotate_day_trades(domain_trades, domain_allocs)
            )
        except Exception as exc:  # noqa: BLE001 — 報表不得因註記失敗中斷
            annotation_extra = {
                "day_trade_annotation": {
                    "rules_version": "unknown",
                    "status": "FAILED",
                    "suspected_day_trade_qty": 0,
                    "same_day_reconciled_qty": 0,
                    "candidates": [],
                    "warnings": [f"ANNOTATION_FAILED:{type(exc).__name__}"],
                }
            }

    audit_path, exc_path = write_audit_files(
        xlsx_path,
        audit,
        rows,
        extra={
            "draft": draft,
            "schema_version": REPORT_SCHEMA_VERSION,
            "fifo_trace_file": str(trace_path),
            "conservation_file": str(conservation_path),
            "amount_conservation_issue_count": len(amount_issues),
            **annotation_extra,
        },
    )

    report = ReportRun(
        id=str(uuid.uuid4()),
        allocation_run_id=run.id,
        report_type="detail_draft" if draft else "detail",
        file_path=str(xlsx_path),
        file_sha256=_sha256_file(xlsx_path),
        status="draft" if draft else "completed",
        schema_version=REPORT_SCHEMA_VERSION,
    )
    session.add(report)
    session.flush()
    return xlsx_path, audit_path, exc_path


def _compute_unsold(
    trades: list[TradeView],
    allocations: list[AllocationView],
    lots: list[OpeningLotView],
) -> list[LotRemaining]:
    sold_buy: dict[str, int] = defaultdict_int()
    sold_lot: dict[str, int] = defaultdict_int()
    for a in allocations:
        if a.buy_trade_id:
            sold_buy[a.buy_trade_id] = sold_buy.get(a.buy_trade_id, 0) + a.quantity
        if a.opening_lot_id:
            sold_lot[a.opening_lot_id] = sold_lot.get(a.opening_lot_id, 0) + a.quantity

    unsold: list[LotRemaining] = []
    order = 0
    for lot in sorted(lots, key=lambda x: (x.buy_date, x.lot_id)):
        rem = lot.quantity - sold_lot.get(lot.lot_id, 0)
        if rem > 0:
            unsold.append(
                LotRemaining(
                    buy_trade_id=None,
                    opening_lot_id=lot.lot_id,
                    available=rem,
                    trade_date=lot.buy_date,
                    unit_price=lot.unit_cost,
                    provenance_order=order,
                )
            )
            order += 1
    for t in sorted([x for x in trades if x.side == "BUY"], key=lambda x: (x.trade_date, x.trade_id)):
        rem = t.quantity - sold_buy.get(t.trade_id, 0)
        if rem > 0:
            unsold.append(
                LotRemaining(
                    buy_trade_id=t.trade_id,
                    opening_lot_id=None,
                    available=rem,
                    trade_date=t.trade_date,
                    unit_price=t.unit_price,
                    provenance_order=order,
                )
            )
            order += 1
    return unsold


def defaultdict_int() -> dict[str, int]:
    return {}
