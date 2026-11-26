"""CR-10B／10C：UAT 實際檔案層故障注入（非僅 mock 布林）。"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy import select

from backend.db.models import FifoAllocation
from backend.db.session import init_db, make_session_factory
from backend.services.allocation_service import match_fifo_for_account
from backend.services.report_service import generate_detail_report
from scripts.uat_fifo_same_day_2236 import (
    TRADES,
    _seed,
    build_uat_checks,
    compute_finance_golden_from_uat_trades,
    resolve_required_outputs,
    verify_detail_xlsx_finance,
)


def _run_synthetic_report(tmp_path: Path):
    """於 tmp DB 跑合成 2236 → match → report（不碰正式 DB）。"""
    db_path = tmp_path / "fault.db"
    engine = init_db(db_path)
    Session = make_session_factory(engine)
    session = Session()
    try:
        account = _seed(session)
        session.commit()
        run, result = match_fifo_for_account(session, account.id)
        session.commit()
        out = tmp_path / "out"
        xlsx, audit_path, exc_path = generate_detail_report(
            session, account.id, out, run_id=run.id, allow_partial=False
        )
        session.commit()
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        alloc_rows = list(
            session.scalars(select(FifoAllocation).where(FifoAllocation.run_id == run.id))
        )
        return {
            "session": session,
            "account": account,
            "run": run,
            "result": result,
            "alloc_rows": alloc_rows,
            "out": out,
            "xlsx": xlsx,
            "audit_path": audit_path,
            "exc_path": exc_path,
            "audit": audit,
        }
    except Exception:
        session.rollback()
        session.close()
        raise


def _base_checks_kwargs(ctx: dict, *, finance_ok: bool, required: dict[str, bool]) -> dict:
    by_type: dict[str, int] = {}
    for a in ctx["result"].allocations:
        by_type[a.match_type] = by_type.get(a.match_type, 0) + a.quantity
    return {
        "required_outputs": required,
        "migration_probe": {
            "day_trade_backfill_ok": True,
            "cash_standard_ok": True,
            "foreign_key_check_empty": True,
            "integrity_ok": True,
        },
        "fresh_schema_has_match_type": True,
        "allocated_qty": sum(a.quantity for a in ctx["result"].allocations),
        "qty_by_match_type": by_type,
        "unsold_qty": sum(u.available for u in ctx["result"].unsold),
        "blocking": bool(ctx["result"].blocking),
        "conservation_ok": True,
        "audit_json": ctx["audit"],
        "integrity_check_result": "ok",
        "h_annotation_non_interference": True,
        "detail_is_draft": "DRAFT" in ctx["xlsx"].name,
        "idempotent": {
            "old_run_preserved": True,
            "old_run_keys_unchanged": True,
            "new_run_keys_equal_old": True,
            "allocated_qty_same": True,
        },
        "formal_db_untouched": True,
        "run_dir_under_data_uat": True,
        "out_dir_under_output_uat": True,
        "detail_xlsx_finance_ok": finance_ok,
    }


def test_cr10b_actual_excel_profit_tamper_fails(tmp_path: Path) -> None:
    """CR-10B：實際修改 Excel 損益 1 元 → finance 驗證失敗 → verdict FAIL。"""
    ctx = _run_synthetic_report(tmp_path)
    golden = compute_finance_golden_from_uat_trades(TRADES)
    ok_before = verify_detail_xlsx_finance(ctx["xlsx"], golden)
    assert ok_before["ok"] is True

    wb = load_workbook(ctx["xlsx"])
    ws = wb.active
    assert ws is not None
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    idx = {h: i for i, h in enumerate(headers)}
    # 找第一筆有損益的列並 +1
    for row in ws.iter_rows(min_row=2, max_col=len(headers)):
        cell = row[idx["損益"]]
        if cell.value is not None:
            cell.value = float(Decimal(str(cell.value)) + Decimal(1))
            break
    wb.save(ctx["xlsx"])

    after = verify_detail_xlsx_finance(ctx["xlsx"], golden)
    assert after["ok"] is False
    assert "profit" in after["diffs"]

    required = resolve_required_outputs(
        audit_json=ctx["audit"],
        out_dir=ctx["out"],
        detail_xlsx=ctx["xlsx"],
        audit_path=ctx["audit_path"],
        exceptions_path=ctx["exc_path"],
    )
    checks = build_uat_checks(**_base_checks_kwargs(ctx, finance_ok=after["ok"], required=required))
    assert checks["detail_xlsx_finance_ok"] is False
    assert all(checks.values()) is False
    ctx["session"].close()


@pytest.mark.parametrize(
    "column",
    ["手續費（買）", "手續費（賣）", "交易稅"],
)
def test_cr10b_actual_excel_fee_column_tamper_fails(tmp_path: Path, column: str) -> None:
    """CR-10B：實際修改 Excel 手續費／稅 1 元 → FAIL。"""
    ctx = _run_synthetic_report(tmp_path)
    golden = compute_finance_golden_from_uat_trades(TRADES)

    wb = load_workbook(ctx["xlsx"])
    ws = wb.active
    assert ws is not None
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    idx = {h: i for i, h in enumerate(headers)}
    for row in ws.iter_rows(min_row=2, max_col=len(headers)):
        cell = row[idx[column]]
        if cell.value is not None:
            cell.value = float(Decimal(str(cell.value)) + Decimal(1))
            break
    wb.save(ctx["xlsx"])

    after = verify_detail_xlsx_finance(ctx["xlsx"], golden)
    assert after["ok"] is False
    ctx["session"].close()


def test_cr10b_blank_excel_replacement_fails(tmp_path: Path) -> None:
    """CR-10B：以空白 Excel 取代明細 → FAIL。"""
    ctx = _run_synthetic_report(tmp_path)
    golden = compute_finance_golden_from_uat_trades(TRADES)
    Workbook().save(ctx["xlsx"])
    result = verify_detail_xlsx_finance(ctx["xlsx"], golden)
    assert result["ok"] is False
    ctx["session"].close()


def test_cr10b_unreadable_excel_replacement_fails(tmp_path: Path) -> None:
    """CR-10B：無法讀取檔案取代明細 → FAIL。"""
    ctx = _run_synthetic_report(tmp_path)
    golden = compute_finance_golden_from_uat_trades(TRADES)
    ctx["xlsx"].write_bytes(b"garbage")
    result = verify_detail_xlsx_finance(ctx["xlsx"], golden)
    assert result["ok"] is False
    ctx["session"].close()


def test_cr10c_delete_fifo_trace_fails_required_outputs(tmp_path: Path) -> None:
    """CR-10C：刪除實際 FIFO Trace → required_outputs.fifo_trace False。"""
    ctx = _run_synthetic_report(tmp_path)
    trace = Path(ctx["audit"]["fifo_trace_file"])
    assert trace.is_file()
    trace.unlink()
    required = resolve_required_outputs(
        audit_json=ctx["audit"],
        out_dir=ctx["out"],
        detail_xlsx=ctx["xlsx"],
        audit_path=ctx["audit_path"],
        exceptions_path=ctx["exc_path"],
    )
    assert required["fifo_trace"] is False
    checks = build_uat_checks(
        **_base_checks_kwargs(ctx, finance_ok=True, required=required)
    )
    assert checks["required_fifo_trace"] is False
    assert all(checks.values()) is False
    ctx["session"].close()


def test_cr10c_delete_conservation_fails_required_outputs(tmp_path: Path) -> None:
    """CR-10C：刪除實際 Conservation CSV → required_outputs.conservation False。"""
    ctx = _run_synthetic_report(tmp_path)
    cons = Path(ctx["audit"]["conservation_file"])
    assert cons.is_file()
    cons.unlink()
    required = resolve_required_outputs(
        audit_json=ctx["audit"],
        out_dir=ctx["out"],
        detail_xlsx=ctx["xlsx"],
        audit_path=ctx["audit_path"],
        exceptions_path=ctx["exc_path"],
    )
    assert required["conservation"] is False
    checks = build_uat_checks(
        **_base_checks_kwargs(ctx, finance_ok=True, required=required)
    )
    assert checks["required_conservation"] is False
    assert all(checks.values()) is False
    ctx["session"].close()


def test_cr10c_tamper_audit_suspected_qty_fails(tmp_path: Path) -> None:
    """CR-10B：修改實際 audit.json 疑似當沖股數 → FAIL。"""
    ctx = _run_synthetic_report(tmp_path)
    audit = dict(ctx["audit"])
    audit["day_trade_annotation"] = dict(audit["day_trade_annotation"])
    audit["day_trade_annotation"]["suspected_day_trade_qty"] = 999
    ctx["audit_path"].write_text(json.dumps(audit, ensure_ascii=False), encoding="utf-8")
    loaded = json.loads(ctx["audit_path"].read_text(encoding="utf-8"))
    required = resolve_required_outputs(
        audit_json=loaded,
        out_dir=ctx["out"],
        detail_xlsx=ctx["xlsx"],
        audit_path=ctx["audit_path"],
        exceptions_path=ctx["exc_path"],
    )
    golden = compute_finance_golden_from_uat_trades(TRADES)
    finance = verify_detail_xlsx_finance(ctx["xlsx"], golden)
    checks = build_uat_checks(
        **_base_checks_kwargs(
            {**ctx, "audit": loaded},
            finance_ok=finance["ok"],
            required=required,
        )
    )
    assert checks["annotation_suspected_exact_1000"] is False
    assert all(checks.values()) is False
    ctx["session"].close()


def test_cr10c_resolve_required_outputs_rejects_directory_named_like_file(
    tmp_path: Path,
) -> None:
    """CR-10C：同名目錄不得當成必要檔案通過。"""
    out = tmp_path / "out"
    out.mkdir()
    fake_trace = out / "FIFO配對及未配對明細_fake.xlsx"
    fake_trace.mkdir()  # 目錄而非檔案
    detail = out / "detail.xlsx"
    detail.write_text("x", encoding="utf-8")
    audit_path = out / "a.json"
    audit = {
        "fifo_trace_file": str(fake_trace),
        "conservation_file": str(out / "missing_cons.csv"),
    }
    audit_path.write_text(json.dumps(audit), encoding="utf-8")
    exc = out / "e.csv"
    exc.write_text("x", encoding="utf-8")
    required = resolve_required_outputs(
        audit_json=audit,
        out_dir=out,
        detail_xlsx=detail,
        audit_path=audit_path,
        exceptions_path=exc,
    )
    assert required["fifo_trace"] is False
    assert required["conservation"] is False
