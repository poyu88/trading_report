"""CR-04：合成 SQLite FIFO 整合測（run 不可變、blocking／DRAFT、冪等）。"""

from __future__ import annotations

import hashlib
import json
import uuid
from decimal import Decimal

from sqlalchemy import func, select

from backend.db.models import (
    Account,
    AllocationRun,
    Broker,
    FifoAllocation,
    ImportBatch,
    OpeningLotRow,
    RawRow,
    ReconciliationIssueRow,
    TradeRow,
)
from backend.db.repositories import find_account_by_label
from backend.domain.exceptions import BlockingExceptionError
from backend.services.allocation_service import match_fifo_for_account
from backend.services.import_service import apply_import
from backend.services.report_service import generate_detail_report


def _hash_table(session, model, cols: list[str]) -> str:
    rows = session.execute(select(*(getattr(model, c) for c in cols)).order_by(model.id)).all()
    payload = json.dumps([list(r) for r in rows], ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _seed_manual(session, *, label: str = "main") -> tuple[Account, str]:
    broker = Broker(id=str(uuid.uuid4()), name=f"it-{uuid.uuid4().hex[:8]}")
    account = Account(id=str(uuid.uuid4()), broker_id=broker.id, account_label=label)
    batch = ImportBatch(
        id=str(uuid.uuid4()),
        account_id=account.id,
        file_sha256=uuid.uuid4().hex + uuid.uuid4().hex[:32],
        filename="it.xls",
        profile_id="statement_html_v1",
        profile_version=1,
        status="completed",
    )
    session.add_all([broker, account, batch])
    session.flush()
    return account, batch.id


def _trade(
    session,
    *,
    account: Account,
    batch_id: str,
    row_index: int,
    side: str,
    qty: int,
    price: str,
    day: str,
    symbol: str = "1111",
    commission: str = "10",
    tax: str = "5",
) -> TradeRow:
    raw = RawRow(
        id=str(uuid.uuid4()),
        batch_id=batch_id,
        sheet_name="",
        row_index=row_index,
        raw_json="{}",
        row_sha256=uuid.uuid4().hex + uuid.uuid4().hex[:32],
        parse_status="ok",
    )
    trade = TradeRow(
        id=str(uuid.uuid4()),
        raw_row_id=raw.id,
        account_id=account.id,
        symbol=symbol,
        name="it",
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
    return trade


def test_sqlite_new_run_old_run_immutable_no_dup_alloc(db_session) -> None:
    account, batch_id = _seed_manual(db_session)
    _trade(
        db_session,
        account=account,
        batch_id=batch_id,
        row_index=1,
        side="BUY",
        qty=1000,
        price="10",
        day="2025-01-01",
    )
    _trade(
        db_session,
        account=account,
        batch_id=batch_id,
        row_index=2,
        side="SELL",
        qty=400,
        price="12",
        day="2025-01-02",
    )
    db_session.commit()

    run1, m1 = match_fifo_for_account(db_session, account.id)
    db_session.commit()
    assert run1.algorithm_version == "fifo_v2_cash_prior_inventory"
    assert sum(a.quantity for a in m1.allocations) == 400

    run1_alloc_ids = {
        a.id
        for a in db_session.scalars(
            select(FifoAllocation).where(FifoAllocation.run_id == run1.id)
        )
    }

    run2, m2 = match_fifo_for_account(db_session, account.id)
    db_session.commit()
    assert run2.id != run1.id
    assert db_session.get(AllocationRun, run1.id) is not None
    still = {
        a.id
        for a in db_session.scalars(
            select(FifoAllocation).where(FifoAllocation.run_id == run1.id)
        )
    }
    assert still == run1_alloc_ids
    total_alloc_rows = db_session.scalar(select(func.count()).select_from(FifoAllocation))
    assert total_alloc_rows == len(m1.allocations) + len(m2.allocations)


def test_sqlite_blocking_status_and_draft_gate(db_session, tmp_path) -> None:
    account, batch_id = _seed_manual(db_session)
    sell = _trade(
        db_session,
        account=account,
        batch_id=batch_id,
        row_index=1,
        side="SELL",
        qty=100,
        price="12",
        day="2025-01-01",
    )
    _trade(
        db_session,
        account=account,
        batch_id=batch_id,
        row_index=2,
        side="BUY",
        qty=100,
        price="10",
        day="2025-01-02",
    )
    db_session.commit()

    run, match = match_fifo_for_account(db_session, account.id)
    db_session.commit()
    assert match.blocking
    assert run.status == "completed_with_issues"
    assert any(i.issue_code == "INSUFFICIENT_PRIOR_BUYS" for i in match.issues)
    issue_rows = list(
        db_session.scalars(
            select(ReconciliationIssueRow).where(ReconciliationIssueRow.run_id == run.id)
        )
    )
    assert any(i.trade_id == sell.id and i.severity == "blocking" for i in issue_rows)

    out = tmp_path / "out"
    try:
        generate_detail_report(db_session, account.id, out, allow_partial=False)
        blocked = False
    except BlockingExceptionError:
        blocked = True
    assert blocked

    xlsx, audit, exc = generate_detail_report(
        db_session, account.id, out, allow_partial=True
    )
    db_session.commit()
    assert "DRAFT" in xlsx.name
    assert audit.exists() and exc.exists()


def test_sqlite_insufficient_one_day_does_not_skip_other_symbols(db_session) -> None:
    account, batch_id = _seed_manual(db_session)
    # A：早賣不足
    _trade(
        db_session,
        account=account,
        batch_id=batch_id,
        row_index=1,
        side="SELL",
        qty=100,
        price="12",
        day="2025-01-01",
        symbol="AAA",
    )
    # B：正常配對
    _trade(
        db_session,
        account=account,
        batch_id=batch_id,
        row_index=2,
        side="BUY",
        qty=200,
        price="10",
        day="2025-01-01",
        symbol="BBB",
    )
    _trade(
        db_session,
        account=account,
        batch_id=batch_id,
        row_index=3,
        side="SELL",
        qty=200,
        price="11",
        day="2025-01-02",
        symbol="BBB",
    )
    db_session.commit()

    _run, match = match_fifo_for_account(db_session, account.id)
    db_session.commit()
    assert match.blocking
    assert any(
        i.issue_code == "INSUFFICIENT_PRIOR_BUYS" and i.detail.get("symbol") == "AAA"
        for i in match.issues
    )
    assert sum(a.quantity for a in match.allocations) == 200
    assert all(a.sell_trade_id for a in match.allocations)


def test_sqlite_rerun_does_not_mutate_fact_tables(db_session) -> None:
    account, batch_id = _seed_manual(db_session)
    lot = OpeningLotRow(
        id=str(uuid.uuid4()),
        account_id=account.id,
        symbol="1111",
        currency="TWD",
        buy_date="2024-01-01",
        quantity=500,
        unit_cost_txt="50",
        approval_note="approved",
        status="approved",
    )
    db_session.add(lot)
    _trade(
        db_session,
        account=account,
        batch_id=batch_id,
        row_index=1,
        side="SELL",
        qty=500,
        price="60",
        day="2025-01-02",
    )
    db_session.commit()

    before = {
        "trades": _hash_table(
            db_session,
            TradeRow,
            [
                "id",
                "account_id",
                "symbol",
                "trade_date",
                "side",
                "quantity",
                "unit_price_txt",
                "commission_txt",
                "tax_txt",
            ],
        ),
        "raw": _hash_table(
            db_session, RawRow, ["id", "batch_id", "row_index", "row_sha256", "parse_status"]
        ),
        "lots": _hash_table(
            db_session,
            OpeningLotRow,
            ["id", "account_id", "symbol", "quantity", "unit_cost_txt", "status"],
        ),
    }

    match_fifo_for_account(db_session, account.id)
    db_session.commit()
    match_fifo_for_account(db_session, account.id)
    db_session.commit()

    after = {
        "trades": _hash_table(
            db_session,
            TradeRow,
            [
                "id",
                "account_id",
                "symbol",
                "trade_date",
                "side",
                "quantity",
                "unit_price_txt",
                "commission_txt",
                "tax_txt",
            ],
        ),
        "raw": _hash_table(
            db_session, RawRow, ["id", "batch_id", "row_index", "row_sha256", "parse_status"]
        ),
        "lots": _hash_table(
            db_session,
            OpeningLotRow,
            ["id", "account_id", "symbol", "quantity", "unit_cost_txt", "status"],
        ),
    }
    assert after == before


def test_sqlite_fees_and_prices_traceable_uuid_varies_logic_stable(
    db_session, fixtures_dir, tmp_path
) -> None:
    src = fixtures_dir / "fifo_fee.html"
    path = tmp_path / "fee.xls"
    path.write_bytes(src.read_bytes())
    apply_import(db_session, path, "測試券商", "fee-acc", "statement_html_v1")
    db_session.commit()
    account = find_account_by_label(db_session, "fee-acc")
    assert account is not None

    run1, m1 = match_fifo_for_account(db_session, account.id)
    db_session.commit()
    run2, m2 = match_fifo_for_account(db_session, account.id)
    db_session.commit()

    assert run1.id != run2.id
    keys1 = sorted(
        (a.buy_trade_id, a.opening_lot_id, a.sell_trade_id, a.quantity, a.sequence_no)
        for a in m1.allocations
    )
    keys2 = sorted(
        (a.buy_trade_id, a.opening_lot_id, a.sell_trade_id, a.quantity, a.sequence_no)
        for a in m2.allocations
    )
    assert keys1 == keys2
    assert sum(a.quantity for a in m1.allocations) == 1200

    trades = list(db_session.scalars(select(TradeRow).where(TradeRow.account_id == account.id)))
    assert any(t.commission_txt not in ("0", "0.0") for t in trades)
    assert all(Decimal(t.unit_price_txt) > 0 for t in trades)
    assert all(t.quantity > 0 for t in trades)
