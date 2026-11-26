"""Phase 3：由正式 Import／FIFO／Report 觀測 D 層摘要（隔離 DB）。"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import FifoAllocation, TradeRow
from backend.domain.models import txt_to_decimal
from backend.golden.compare_c_d import trade_source_fingerprint
from backend.reports.field_schema import HEADERS
from backend.services.allocation_service import match_fifo_for_account
from backend.services.fifo_matcher import MATCH_TYPE_SAME_DAY, MATCH_TYPE_STANDARD
from backend.services.import_service import apply_import
from backend.services.report_service import generate_detail_report


def trade_row_fingerprint(trade: TradeRow) -> str:
    """由 DB TradeRow 建立來源指紋。"""
    return trade_source_fingerprint(
        symbol=trade.symbol,
        trade_date=trade.trade_date,
        side=trade.side,
        quantity=trade.quantity,
        unit_price=txt_to_decimal(trade.unit_price_txt),
        gross_amount=txt_to_decimal(trade.gross_amount_txt),
        commission=txt_to_decimal(trade.commission_txt),
        tax=txt_to_decimal(trade.tax_txt),
        interest=txt_to_decimal(trade.interest_txt),
    )


def sum_detail_xlsx_finance(xlsx_path: Path) -> dict[str, Decimal]:
    """加總明細 Excel 財務欄（讀取 only）。"""
    wb = load_workbook(xlsx_path, data_only=True)
    ws = wb.active
    if ws is None:
        raise ValueError("no_active_sheet")
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    if headers != HEADERS:
        raise ValueError("header_mismatch")
    idx = {h: i for i, h in enumerate(HEADERS)}
    out = {
        "buy_qty": Decimal(0),
        "sell_qty": Decimal(0),
        "buy_commission": Decimal(0),
        "sell_commission": Decimal(0),
        "tax": Decimal(0),
        "interest": Decimal(0),
        "cost": Decimal(0),
        "income": Decimal(0),
        "profit": Decimal(0),
    }
    for row in ws.iter_rows(min_row=2, max_col=len(HEADERS), values_only=True):
        if all(v is None for v in row):
            continue
        for col, key in (
            ("股數（買）", "buy_qty"),
            ("股數（賣）", "sell_qty"),
            ("手續費（買）", "buy_commission"),
            ("手續費（賣）", "sell_commission"),
            ("交易稅", "tax"),
            ("利息", "interest"),
            ("成本", "cost"),
            ("收入", "income"),
            ("損益", "profit"),
        ):
            val = row[idx[col]]
            if val is not None:
                out[key] += Decimal(str(val))
    return out


def collect_actual_d(
    session: Session,
    *,
    account_id: str,
    run_id: str,
    xlsx_path: Path,
    match_result: Any,
) -> dict[str, Any]:
    """自正式管線觀測值組裝 D 層摘要。"""
    trades = list(session.scalars(select(TradeRow).where(TradeRow.account_id == account_id)))
    allocs = list(
        session.scalars(select(FifoAllocation).where(FifoAllocation.run_id == run_id))
    )
    id_to_fp = {t.id: trade_row_fingerprint(t) for t in trades}
    buy_gross = sum(
        (txt_to_decimal(t.gross_amount_txt) for t in trades if t.side == "BUY"),
        Decimal(0),
    )
    sell_gross = sum(
        (txt_to_decimal(t.gross_amount_txt) for t in trades if t.side == "SELL"),
        Decimal(0),
    )
    buy_commission = sum(
        (txt_to_decimal(t.commission_txt) for t in trades if t.side == "BUY"),
        Decimal(0),
    )
    sell_commission = sum(
        (txt_to_decimal(t.commission_txt) for t in trades if t.side == "SELL"),
        Decimal(0),
    )
    tax = sum((txt_to_decimal(t.tax_txt) for t in trades), Decimal(0))
    interest = sum((txt_to_decimal(t.interest_txt) for t in trades), Decimal(0))
    xlsx = sum_detail_xlsx_finance(xlsx_path)

    standard = same_day = 0
    for a in allocs:
        if a.match_type == MATCH_TYPE_STANDARD:
            standard += a.allocated_quantity
        elif a.match_type == MATCH_TYPE_SAME_DAY:
            same_day += a.allocated_quantity

    allocation_fingerprints = [
        {
            "match_type": a.match_type,
            "quantity": a.allocated_quantity,
            "buy_fp": id_to_fp.get(a.buy_trade_id or "", ""),
            "sell_fp": id_to_fp.get(a.sell_trade_id, ""),
        }
        for a in allocs
    ]
    return {
        "trade_count": len(trades),
        "buy_qty": sum(t.quantity for t in trades if t.side == "BUY"),
        "sell_qty": sum(t.quantity for t in trades if t.side == "SELL"),
        "buy_gross": buy_gross,
        "sell_gross": sell_gross,
        "buy_commission": buy_commission,
        "sell_commission": sell_commission,
        "tax": tax,
        "interest": interest,
        "cost": xlsx["cost"],
        "income": xlsx["income"],
        "realized_pnl": xlsx["profit"],
        "open_quantity": sum(u.available for u in match_result.unsold),
        "open_cost": Decimal(0),  # 報表未售成本由 realized 對照；此處以 unsold 股數為主
        "standard_fifo_allocated_qty": standard,
        "same_day_reconciled_qty": same_day,
        "unmatched_sell_qty": sum(
            int((i.detail or {}).get("unmatched_quantity") or 0)
            for i in match_result.issues
            if i.issue_code == "INSUFFICIENT_PRIOR_BUYS"
        ),
        "unsold_buy_qty": sum(u.available for u in match_result.unsold),
        "allocation_fingerprints": allocation_fingerprints,
        "trade_fingerprints": [trade_row_fingerprint(t) for t in trades],
        "xlsx_finance": {k: str(v) for k, v in xlsx.items()},
    }


def run_import_match_report(
    session: Session,
    *,
    source_path: Path,
    broker_name: str,
    account_label: str,
    profile_id: str,
    out_dir: Path,
) -> dict[str, Any]:
    """正式 Parser／Import／FIFO／Report；呼叫端負責 commit。"""
    from backend.db.repositories import find_account_by_label

    imp = apply_import(session, source_path, broker_name, account_label, profile_id)
    session.flush()
    account = find_account_by_label(session, account_label)
    if account is None:
        raise RuntimeError("account_missing_after_import")
    run, match = match_fifo_for_account(session, account.id)
    session.flush()
    xlsx, audit_path, exc_path = generate_detail_report(
        session,
        account.id,
        out_dir,
        run_id=run.id,
        allow_partial=bool(match.blocking),
    )
    session.flush()
    actual = collect_actual_d(
        session,
        account_id=account.id,
        run_id=run.id,
        xlsx_path=xlsx,
        match_result=match,
    )
    return {
        "import_result": imp,
        "account_id": account.id,
        "run_id": run.id,
        "match": match,
        "xlsx": xlsx,
        "audit_path": audit_path,
        "exc_path": exc_path,
        "actual_d": actual,
        "detail_is_draft": "DRAFT" in xlsx.name,
    }
