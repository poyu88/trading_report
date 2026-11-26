"""CR-07／08／09：report annotation ON／OFF 與 fault injection。"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from backend.db.models import (
    Account,
    Broker,
    FifoAllocation,
    ImportBatch,
    RawRow,
    TradeRow,
)
from backend.services.allocation_service import match_fifo_for_account
from backend.services.report_service import generate_detail_report


def _seed(session, *, label: str = "ann-rpt") -> Account:
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


def test_report_annotation_on_off_finance_equal(db_session, tmp_path: Path) -> None:
    """CR-07／09：include_day_trade_annotation ON／OFF 財務鍵全等。"""
    account = _seed(db_session)
    db_session.commit()
    run, result = match_fifo_for_account(db_session, account.id)
    db_session.commit()
    assert not result.blocking

    snap_before = _finance_snapshot(db_session, run.id, account.id)

    out_off = tmp_path / "off"
    out_on = tmp_path / "on"
    xlsx_off, audit_off, _ = generate_detail_report(
        db_session,
        account.id,
        out_off,
        run_id=run.id,
        include_day_trade_annotation=False,
    )
    db_session.commit()
    xlsx_on, audit_on, _ = generate_detail_report(
        db_session,
        account.id,
        out_on,
        run_id=run.id,
        include_day_trade_annotation=True,
    )
    db_session.commit()

    assert snap_before == _finance_snapshot(db_session, run.id, account.id)
    assert xlsx_off.exists() and xlsx_on.exists()

    off_audit = json.loads(audit_off.read_text(encoding="utf-8"))
    on_audit = json.loads(audit_on.read_text(encoding="utf-8"))
    assert "day_trade_annotation" not in off_audit
    assert "day_trade_annotation" in on_audit
    assert on_audit["day_trade_annotation"]["suspected_day_trade_qty"] >= 0


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
