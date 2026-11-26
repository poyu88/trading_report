"""Phase 3：由正式 Import／FIFO／Report 觀測 D 層摘要（隔離 DB）。"""

from __future__ import annotations

import csv
import json
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
from backend.reports.fifo_trace_writer import HEADERS as TRACE_HEADERS
from backend.services.allocation_service import match_fifo_for_account
from backend.services.fifo_matcher import MATCH_TYPE_SAME_DAY, MATCH_TYPE_STANDARD
from backend.services.import_service import apply_import
from backend.services.report_service import generate_detail_report

CONSERVATION_REQUIRED_COLS = {
    "trade_id",
    "side",
    "source_qty",
    "A_original_gross",
    "F_conservation_ok",
    "commission",
    "tax",
    "interest",
}

# Conservation CSV 合法布林字串（Python str(bool) 與小寫）
_CONSERVATION_TRUE = frozenset({"true"})
_CONSERVATION_FALSE = frozenset({"false"})
_CONSERVATION_LEGAL = _CONSERVATION_TRUE | _CONSERVATION_FALSE


def decide_gold004_verdict(
    *,
    compare_ok: bool,
    finance_ok: bool,
    per_line_ok: bool,
    artifacts_ok: bool,
    formal_db_untouched: bool,
    pending_data: list[str],
) -> dict[str, Any]:
    """GOLD-004 最終判定。

    必要驗收（compare／finance／per_line／artifacts／正式 DB 指紋）任一失敗 → FAIL。
    PARTIAL 僅用於已登記資料不足，且必要驗證全過。
    """
    necessary_ok = (
        bool(compare_ok)
        and bool(finance_ok)
        and bool(per_line_ok)
        and bool(artifacts_ok)
        and bool(formal_db_untouched)
    )
    pending = [p for p in pending_data if p]
    if not necessary_ok:
        verdict = "FAIL"
        exit_code = 1
    elif pending:
        verdict = "PARTIAL"
        exit_code = 0
    else:
        verdict = "PASS"
        exit_code = 0
    return {
        "verdict": verdict,
        "exit_code": exit_code,
        "necessary_ok": necessary_ok,
        "pending_data": pending,
    }


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


def observe_open_cost_from_detail_xlsx(xlsx_path: Path) -> dict[str, Any]:
    """由明細 Excel 觀測未平倉成本（賣出股數空且買進股數>0 之成本加總）。

    Returns:
        ``open_quantity`` 觀測列股數合計、``open_cost``、``open_cost_status``。
        有未平倉列但無法讀成本 → ``NOT_VERIFIED``。
    """
    wb = load_workbook(xlsx_path, data_only=True)
    ws = wb.active
    if ws is None:
        return {
            "open_quantity": 0,
            "open_cost": None,
            "open_cost_status": "NOT_VERIFIED",
        }
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    if headers != HEADERS:
        return {
            "open_quantity": 0,
            "open_cost": None,
            "open_cost_status": "NOT_VERIFIED",
        }
    idx = {h: i for i, h in enumerate(HEADERS)}
    open_qty = 0
    open_cost = Decimal(0)
    saw_open = False
    for row in ws.iter_rows(min_row=2, max_col=len(HEADERS), values_only=True):
        if all(v is None for v in row):
            continue
        sell_qty = row[idx["股數（賣）"]]
        buy_qty = row[idx["股數（買）"]]
        sell_empty = sell_qty is None or Decimal(str(sell_qty)) == 0
        buy_n = int(buy_qty or 0)
        if sell_empty and buy_n > 0:
            saw_open = True
            open_qty += buy_n
            cost_val = row[idx["成本"]]
            if cost_val is None:
                return {
                    "open_quantity": open_qty,
                    "open_cost": None,
                    "open_cost_status": "NOT_VERIFIED",
                }
            open_cost += Decimal(str(cost_val))
    if not saw_open and open_qty == 0:
        return {
            "open_quantity": 0,
            "open_cost": Decimal(0),
            "open_cost_status": "VERIFIED_ZERO",
        }
    return {
        "open_quantity": open_qty,
        "open_cost": open_cost,
        "open_cost_status": "VERIFIED",
    }


def read_fifo_trace_rows(trace_path: Path) -> list[dict[str, Any]]:
    """讀取 FIFO Trace 列為 dict（內容驗證用）。"""
    wb = load_workbook(trace_path, data_only=True)
    ws = wb.active
    if ws is None:
        raise ValueError("trace_no_active_sheet")
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    if headers != TRACE_HEADERS:
        raise ValueError("trace_header_mismatch")
    idx = {h: i for i, h in enumerate(headers)}
    rows: list[dict[str, Any]] = []
    for row in ws.iter_rows(min_row=2, max_col=len(headers), values_only=True):
        if all(v is None for v in row):
            continue
        rows.append(
            {
                "row_kind": row[idx["列語意"]],
                "symbol": row[idx["股票代號"]],
                "quantity": row[idx["股數"]],
                "commission": row[idx["手續費"]],
                "tax": row[idx["交易稅"]],
                "interest": row[idx["利息"]],
                "cost": row[idx["成本"]],
                "income": row[idx["收入"]],
                "profit": row[idx["損益"]],
                "buy_trade_id": row[idx["buy_trade_id"]],
                "sell_trade_id": row[idx["sell_trade_id"]],
                "match_type": row[idx["match_type"]],
            }
        )
    return rows


def verify_audit_artifacts_content(
    *,
    audit_path: Path,
    exceptions_path: Path,
    out_dir: Path,
) -> dict[str, Any]:
    """CR-10C：核對 Audit／Trace／Conservation／Exceptions 必要格式與欄位（非僅存在）。"""
    errors: list[str] = []
    checks: dict[str, bool] = {}
    if not audit_path.is_file():
        return {"ok": False, "checks": {}, "errors": ["audit_missing"]}
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    required_audit = {
        "conservation_ok",
        "fifo_trace_file",
        "conservation_file",
        "trade_count",
        "allocation_count",
        "draft",
    }
    missing_audit = sorted(required_audit - set(audit))
    checks["audit_required_keys"] = not missing_audit
    if missing_audit:
        errors.append(f"audit_missing_keys:{','.join(missing_audit)}")

    trace_raw = audit.get("fifo_trace_file")
    cons_raw = audit.get("conservation_file")
    trace_path = Path(str(trace_raw)) if trace_raw else None
    cons_path = Path(str(cons_raw)) if cons_raw else None
    out_r = out_dir.resolve()

    def _under_out(p: Path | None) -> bool:
        if p is None or not p.is_file():
            return False
        try:
            resolved = p.resolve()
        except OSError:
            return False
        return out_r in resolved.parents or resolved == out_r

    checks["trace_under_out"] = _under_out(trace_path)
    checks["conservation_under_out"] = _under_out(cons_path)
    if not checks["trace_under_out"]:
        errors.append("trace_path_invalid")
    if not checks["conservation_under_out"]:
        errors.append("conservation_path_invalid")

    if checks["trace_under_out"] and trace_path is not None:
        try:
            trows = read_fifo_trace_rows(trace_path)
            checks["trace_has_rows"] = len(trows) > 0
            checks["trace_has_matched_or_unsold"] = any(
                r.get("row_kind") in {"MATCHED", "UNSOLD_BUY", "UNMATCHED_SELL"} for r in trows
            )
            if not checks["trace_has_rows"]:
                errors.append("trace_empty")
        except ValueError as exc:
            checks["trace_headers_ok"] = False
            errors.append(f"trace_read:{exc}")
        else:
            checks["trace_headers_ok"] = True

    audit_cons = audit.get("conservation_ok")
    checks["audit_conservation_ok_is_bool"] = isinstance(audit_cons, bool)
    if not checks["audit_conservation_ok_is_bool"]:
        errors.append("audit_conservation_ok_not_bool")

    rows_all_ok = False
    if checks["conservation_under_out"] and cons_path is not None:
        with cons_path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            cols = set(reader.fieldnames or [])
            missing = sorted(CONSERVATION_REQUIRED_COLS - cols)
            checks["conservation_required_cols"] = not missing
            if missing:
                errors.append(f"conservation_missing_cols:{','.join(missing)}")
            body = list(reader)
            checks["conservation_has_rows"] = len(body) > 0
            if not body:
                errors.append("conservation_empty")
                checks["conservation_ok_values_legal"] = False
                checks["conservation_all_rows_ok"] = False
                checks["audit_conservation_matches_rows"] = False
            else:
                raw_vals = [str(r.get("F_conservation_ok", "")).strip() for r in body]
                lower_vals = [v.lower() for v in raw_vals]
                legal = all(v in _CONSERVATION_LEGAL for v in lower_vals)
                checks["conservation_ok_values_legal"] = legal
                if not legal:
                    errors.append("conservation_ok_illegal_values")
                # 不得僅確認字串存在；須核對實際守恆狀態
                rows_all_ok = legal and all(v in _CONSERVATION_TRUE for v in lower_vals)
                checks["conservation_all_rows_ok"] = rows_all_ok
                if legal and not rows_all_ok:
                    errors.append("conservation_row_failed")
                if checks["audit_conservation_ok_is_bool"]:
                    matches = bool(audit_cons) == rows_all_ok
                    checks["audit_conservation_matches_rows"] = matches
                    if not matches:
                        errors.append("audit_conservation_mismatch_csv")
                else:
                    checks["audit_conservation_matches_rows"] = False
    else:
        checks["conservation_ok_values_legal"] = False
        checks["conservation_all_rows_ok"] = False
        checks["audit_conservation_matches_rows"] = False

    if not exceptions_path.is_file():
        checks["exceptions_exists"] = False
        errors.append("exceptions_missing")
    else:
        checks["exceptions_exists"] = True
        exc_text = exceptions_path.read_text(encoding="utf-8-sig")
        header = exc_text.splitlines()[0].lower() if exc_text else ""
        # 現行 exceptions 表頭含 issue_id／code／severity
        checks["exceptions_has_header"] = "code" in header and "severity" in header
        if not checks["exceptions_has_header"]:
            errors.append("exceptions_header_mismatch")

    return {"ok": all(checks.values()) and not errors, "checks": checks, "errors": errors, "audit": audit}


def collect_actual_d(
    session: Session,
    *,
    account_id: str,
    run_id: str,
    xlsx_path: Path,
    match_result: Any,
) -> dict[str, Any]:
    """自正式管線觀測值組裝 D 層摘要（不得用 expected 填補）。"""
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
    unsold_qty = sum(u.available for u in match_result.unsold)
    open_obs = observe_open_cost_from_detail_xlsx(xlsx_path)
    # 未平倉股數以 match 結果為準；成本僅來自報表觀測
    if unsold_qty == 0:
        open_cost: Decimal | None = Decimal(0)
        open_cost_status = "VERIFIED_ZERO"
    else:
        open_cost = open_obs.get("open_cost")
        open_cost_status = str(open_obs.get("open_cost_status") or "NOT_VERIFIED")
        if open_cost is None:
            open_cost_status = "NOT_VERIFIED"

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
        "open_quantity": unsold_qty,
        "open_cost": open_cost,
        "open_cost_status": open_cost_status,
        "standard_fifo_allocated_qty": standard,
        "same_day_reconciled_qty": same_day,
        "unmatched_sell_qty": sum(
            int((i.detail or {}).get("unmatched_quantity") or 0)
            for i in match_result.issues
            if i.issue_code == "INSUFFICIENT_PRIOR_BUYS"
        ),
        "unsold_buy_qty": unsold_qty,
        "allocation_fingerprints": allocation_fingerprints,
        "trade_fingerprints": [trade_row_fingerprint(t) for t in trades],
        "trade_id_to_fp": id_to_fp,
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
    artifacts = verify_audit_artifacts_content(
        audit_path=audit_path,
        exceptions_path=exc_path,
        out_dir=out_dir,
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
        "artifacts": artifacts,
    }
