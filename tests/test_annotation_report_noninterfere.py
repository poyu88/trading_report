"""CR-07／08／09：report annotation ON／OFF 與 fault injection。"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from backend.db.models import (
    Account,
    Broker,
    FifoAllocation,
    ImportBatch,
    RawRow,
    TradeRow,
)
from backend.reports.field_schema import HEADERS
from backend.services.allocation_service import match_fifo_for_account
from backend.services.report_service import generate_detail_report

# 與 backend/reports/audit_writer.py payload 對齊；缺任一鍵 → fail（禁止 if key in）
REQUIRED_AUDIT_KEYS = (
    "conservation_ok",
    "blocking_issue_count",
    "commission_total",
    "tax_total",
    "trade_count",
    "allocation_count",
    "buy_count",
    "sell_count",
    "detail_row_count",
)


def _seed(
    session,
    *,
    label: str = "ann-rpt",
    rows: list[tuple[str, str, int, str, str, str]] | None = None,
) -> Account:
    broker = Broker(id=str(uuid.uuid4()), name=f"ann-{uuid.uuid4().hex[:8]}")
    account = Account(id=str(uuid.uuid4()), broker_id=broker.id, account_label=label)
    batch = ImportBatch(
        id=str(uuid.uuid4()),
        account_id=account.id,
        file_sha256=uuid.uuid4().hex + uuid.uuid4().hex[:32],
        filename="ann.xls",
        profile_id="statement_html_v1",
        profile_version=1,
        status="completed",
    )
    session.add_all([broker, account, batch])
    session.flush()

    if rows is None:
        rows = [
            ("2025-03-20", "BUY", 1000, "72", "20", "0"),
            ("2025-03-20", "SELL", 1000, "70", "20", "105"),
        ]
    for idx, (day, side, qty, price, commission, tax) in enumerate(rows, start=1):
        raw = RawRow(
            id=str(uuid.uuid4()),
            batch_id=batch.id,
            sheet_name="S",
            row_index=idx,
            raw_json="{}",
            row_sha256=uuid.uuid4().hex + uuid.uuid4().hex[:32],
            parse_status="ok",
        )
        trade = TradeRow(
            id=str(uuid.uuid4()),
            raw_row_id=raw.id,
            account_id=account.id,
            symbol="2236",
            name="syn",
            trade_date=day,
            side=side,
            trade_type="CASH",
            currency="TWD",
            quantity=qty,
            unit_price_txt=price,
            gross_amount_txt=str(Decimal(price) * qty),
            commission_txt=commission,
            tax_txt=tax,
            interest_txt="0",
            raw_payload_json="{}",
        )
        session.add_all([raw, trade])
    session.flush()
    return account


def _finance_snapshot(session, run_id: str, account_id: str) -> dict:
    trades = list(session.scalars(select(TradeRow).where(TradeRow.account_id == account_id)))
    allocs = list(
        session.scalars(select(FifoAllocation).where(FifoAllocation.run_id == run_id))
    )
    return {
        "allocs": [
            (a.buy_trade_id, a.sell_trade_id, a.allocated_quantity, a.match_type)
            for a in allocs
        ],
        "buy_gross": sorted(t.gross_amount_txt for t in trades if t.side == "BUY"),
        "sell_gross": sorted(t.gross_amount_txt for t in trades if t.side == "SELL"),
        "commission": sorted(t.commission_txt for t in trades),
        "tax": sorted(t.tax_txt for t in trades),
    }


def _xlsx_finance_matrix(path: Path) -> list[tuple]:
    """讀取明細 A–W 財務儲存格（含表頭，排除僅 metadata 差異）。"""
    wb = load_workbook(path, data_only=True)
    ws = wb.active
    assert [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))] == HEADERS
    rows: list[tuple] = []
    for row in ws.iter_rows(min_row=2, max_col=len(HEADERS), values_only=True):
        rows.append(tuple(row))
    return rows


def _assert_on_off_equal(
    db_session,
    tmp_path: Path,
    account: Account,
    *,
    allow_partial: bool = False,
):
    run, result = match_fifo_for_account(db_session, account.id)
    db_session.commit()
    snap_before = _finance_snapshot(db_session, run.id, account.id)

    out_off = tmp_path / f"off_{account.account_label}"
    out_on = tmp_path / f"on_{account.account_label}"
    xlsx_off, audit_off, exc_off = generate_detail_report(
        db_session,
        account.id,
        out_off,
        run_id=run.id,
        include_day_trade_annotation=False,
        allow_partial=allow_partial,
    )
    db_session.commit()
    xlsx_on, audit_on, exc_on = generate_detail_report(
        db_session,
        account.id,
        out_on,
        run_id=run.id,
        include_day_trade_annotation=True,
        allow_partial=allow_partial,
    )
    db_session.commit()

    assert snap_before == _finance_snapshot(db_session, run.id, account.id)
    assert xlsx_off.exists() and xlsx_on.exists()
    assert _xlsx_finance_matrix(xlsx_off) == _xlsx_finance_matrix(xlsx_on)
    assert exc_off.exists() and exc_on.exists()
    assert exc_off.read_bytes() == exc_on.read_bytes()

    cons_off = next(out_off.glob("*守恆*"), None) or next(out_off.glob("*conservation*"), None)
    cons_on = next(out_on.glob("*守恆*"), None) or next(out_on.glob("*conservation*"), None)
    assert cons_off is not None and cons_on is not None, "conservation CSV 必須存在"
    assert cons_off.read_bytes() == cons_on.read_bytes()

    off_audit = json.loads(audit_off.read_text(encoding="utf-8"))
    on_audit = json.loads(audit_on.read_text(encoding="utf-8"))
    assert "day_trade_annotation" not in off_audit
    assert "day_trade_annotation" in on_audit
    for key in REQUIRED_AUDIT_KEYS:
        assert key in off_audit, f"OFF audit 缺必要鍵 {key}"
        assert key in on_audit, f"ON audit 缺必要鍵 {key}"
        assert off_audit[key] == on_audit[key], f"audit[{key}] ON/OFF 不一致"

    return result


def test_report_annotation_on_off_finance_equal(db_session, tmp_path: Path) -> None:
    """CR-07／09：ON／OFF 財務鍵與 Excel A–W／conservation／exceptions 全等。"""
    account = _seed(db_session)
    db_session.commit()
    result = _assert_on_off_equal(db_session, tmp_path, account)
    assert not result.blocking


def test_cr07_unsold_remainder_on_off_equal(db_session, tmp_path: Path) -> None:
    """CR-07：未平倉剩餘（僅買／賣少）ON／OFF 財務仍全等。"""
    account = _seed(
        db_session,
        label="ann-unsold",
        rows=[
            ("2025-03-21", "BUY", 1000, "72", "20", "0"),
            ("2025-03-21", "SELL", 400, "70", "20", "42"),
        ],
    )
    db_session.commit()
    result = _assert_on_off_equal(db_session, tmp_path, account)
    assert not result.blocking
    assert sum(u.available for u in result.unsold) == 600


def test_cr07_partial_match_on_off_equal(db_session, tmp_path: Path) -> None:
    """CR-07：部分配對（跨日庫存＋當日）ON／OFF 財務仍全等。"""
    account = _seed(
        db_session,
        label="ann-partial",
        rows=[
            ("2025-03-18", "BUY", 500, "70", "15", "0"),
            ("2025-03-20", "BUY", 500, "72", "15", "0"),
            ("2025-03-20", "SELL", 800, "75", "20", "90"),
        ],
    )
    db_session.commit()
    result = _assert_on_off_equal(db_session, tmp_path, account)
    assert not result.blocking
    assert sum(a.quantity for a in result.allocations) == 800
    assert sum(u.available for u in result.unsold) == 200


def test_cr07_unmatched_sell_draft_on_off_equal(db_session, tmp_path: Path) -> None:
    """CR-07：未配對賣出（DRAFT／allow_partial）ON／OFF 財務仍全等。"""
    account = _seed(
        db_session,
        label="ann-unmatched",
        rows=[
            ("2025-03-22", "BUY", 100, "72", "10", "0"),
            ("2025-03-22", "SELL", 500, "70", "20", "53"),
        ],
    )
    db_session.commit()
    result = _assert_on_off_equal(db_session, tmp_path, account, allow_partial=True)
    assert result.blocking
    assert any(i.issue_code == "INSUFFICIENT_PRIOR_BUYS" for i in result.issues)


def test_report_annotation_fault_still_writes_detail(
    db_session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CR-08：annotation 內部拋錯 → audit 含 ANNOTATION_FAILED；detail 仍成功。"""
    from backend.services import report_service as rpt

    account = _seed(db_session, label="ann-fault")
    db_session.commit()
    run, result = match_fifo_for_account(db_session, account.id)
    db_session.commit()
    assert not result.blocking
    snap = _finance_snapshot(db_session, run.id, account.id)

    def _boom(*_a, **_k):
        raise RuntimeError("inject")

    monkeypatch.setattr(rpt, "annotate_day_trades", _boom)

    out = tmp_path / "fault"
    xlsx, audit_path, exc_path = generate_detail_report(
        db_session,
        account.id,
        out,
        run_id=run.id,
        include_day_trade_annotation=True,
    )
    db_session.commit()

    assert xlsx.exists() and audit_path.exists() and exc_path.exists()
    assert "DRAFT" not in xlsx.name
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    warnings = audit["day_trade_annotation"]["warnings"]
    assert any(w.startswith("ANNOTATION_FAILED:") for w in warnings)
    assert snap == _finance_snapshot(db_session, run.id, account.id)


def test_cr04_annotation_prep_fault_isolated(
    db_session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CR-04：annotation 專用資料準備失敗 → FAILED warning；主報表仍產出。"""
    from backend.services import report_service as rpt

    account = _seed(db_session, label="ann-prep")
    db_session.commit()
    run, result = match_fifo_for_account(db_session, account.id)
    db_session.commit()
    assert not result.blocking
    snap = _finance_snapshot(db_session, run.id, account.id)

    real_trade = rpt.Trade

    class _BoomTrade:
        def __init__(self, *a, **k):
            raise RuntimeError("prep fault")

    monkeypatch.setattr(rpt, "Trade", _BoomTrade)

    out = tmp_path / "prep-fault"
    xlsx, audit_path, _ = generate_detail_report(
        db_session,
        account.id,
        out,
        run_id=run.id,
        include_day_trade_annotation=True,
    )
    db_session.commit()
    assert xlsx.exists()
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    warnings = audit["day_trade_annotation"]["warnings"]
    assert any(w.startswith("ANNOTATION_FAILED:") for w in warnings)
    assert audit["day_trade_annotation"]["suspected_day_trade_qty"] == 0
    assert audit["day_trade_annotation"]["candidates"] == []
    assert snap == _finance_snapshot(db_session, run.id, account.id)
    monkeypatch.setattr(rpt, "Trade", real_trade)


def test_cr04_annotation_off_skips_prep(
    monkeypatch: pytest.MonkeyPatch, db_session, tmp_path: Path
) -> None:
    """CR-04：Annotation OFF 不得執行 annotation 專用資料準備。"""
    from backend.services import report_service as rpt

    account = _seed(db_session, label="ann-off")
    db_session.commit()
    run, result = match_fifo_for_account(db_session, account.id)
    db_session.commit()
    assert not result.blocking

    calls = {"n": 0}

    class _CountingTrade:
        def __init__(self, *a, **k):
            calls["n"] += 1
            raise AssertionError("annotation prep must not run when OFF")

    monkeypatch.setattr(rpt, "Trade", _CountingTrade)
    out = tmp_path / "off-skip"
    xlsx, audit_path, _ = generate_detail_report(
        db_session,
        account.id,
        out,
        run_id=run.id,
        include_day_trade_annotation=False,
    )
    db_session.commit()
    assert xlsx.exists()
    assert calls["n"] == 0
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert "day_trade_annotation" not in audit
