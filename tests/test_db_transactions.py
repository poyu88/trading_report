"""DB-03：原子性回滾、外鍵與中途錯誤不污染既有紀錄。"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.db.models import Account, Broker, ImportBatch, RawRow, TradeRow
from backend.db.session import create_db_engine, init_db, make_session_factory


@pytest.fixture()
def engine(tmp_path: Path):
    return init_db(tmp_path / "tx.db")


@pytest.fixture()
def session_factory(engine):
    return make_session_factory(engine)


def test_foreign_keys_pragma_is_on(engine) -> None:
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


def test_orphan_account_insert_is_rejected(session_factory) -> None:
    session = session_factory()
    try:
        session.add(
            Account(id=str(uuid.uuid4()), broker_id="missing-broker", account_label="orphan")
        )
        with pytest.raises(IntegrityError):
            session.commit()
    finally:
        session.rollback()
        session.close()


def test_trade_check_constraint_rejects_invalid_side(session_factory) -> None:
    session = session_factory()
    try:
        broker = Broker(id=str(uuid.uuid4()), name="tx-broker")
        account = Account(
            id=str(uuid.uuid4()), broker_id=broker.id, account_label="main"
        )
        batch = ImportBatch(
            id=str(uuid.uuid4()),
            account_id=account.id,
            file_sha256="a" * 64,
            filename="x.xls",
            profile_id="statement_html_v1",
            profile_version=1,
            status="completed",
        )
        raw = RawRow(
            id=str(uuid.uuid4()),
            batch_id=batch.id,
            sheet_name="",
            row_index=1,
            raw_json="{}",
            row_sha256="b" * 64,
            parse_status="ok",
        )
        session.add_all([broker, account, batch, raw])
        session.flush()
        session.add(
            TradeRow(
                id=str(uuid.uuid4()),
                raw_row_id=raw.id,
                account_id=account.id,
                symbol="0050",
                name="測試",
                trade_date="2026-01-05",
                side="HOLD",
                trade_type="CASH",
                currency="TWD",
                quantity=100,
                unit_price_txt="10",
                gross_amount_txt="1000",
                commission_txt="0",
                tax_txt="0",
                interest_txt="0",
                raw_payload_json="{}",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
    finally:
        session.rollback()
        session.close()


def test_mid_transaction_error_rolls_back_without_polluting(session_factory) -> None:
    """既有 broker 保留；失敗批次的 account／trades 不得殘留。"""
    keep_id = str(uuid.uuid4())
    session = session_factory()
    try:
        session.add(Broker(id=keep_id, name="keep-me"))
        session.commit()
    finally:
        session.close()

    session = session_factory()
    try:
        broker = session.get(Broker, keep_id)
        assert broker is not None
        account = Account(
            id=str(uuid.uuid4()), broker_id=keep_id, account_label="temp"
        )
        batch = ImportBatch(
            id=str(uuid.uuid4()),
            account_id=account.id,
            file_sha256="c" * 64,
            filename="fail.xls",
            profile_id="statement_html_v1",
            profile_version=1,
            status="completed",
        )
        session.add_all([account, batch])
        session.flush()
        # 故意寫入不存在的 batch_id，觸發外鍵失敗
        session.add(
            RawRow(
                id=str(uuid.uuid4()),
                batch_id="00000000-0000-0000-0000-000000000000",
                sheet_name="",
                row_index=1,
                raw_json="{}",
                row_sha256="d" * 64,
                parse_status="ok",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
    finally:
        session.close()

    verify = session_factory()
    try:
        assert verify.get(Broker, keep_id) is not None
        assert verify.execute(text("SELECT COUNT(*) FROM accounts")).scalar_one() == 0
        assert verify.execute(text("SELECT COUNT(*) FROM import_batches")).scalar_one() == 0
        assert verify.execute(text("SELECT COUNT(*) FROM raw_rows")).scalar_one() == 0
        assert verify.execute(text("SELECT COUNT(*) FROM trades")).scalar_one() == 0
        assert verify.execute(text("SELECT COUNT(*) FROM brokers")).scalar_one() == 1
    finally:
        verify.close()


def test_wal_or_default_journal_is_usable(tmp_path: Path) -> None:
    db_path = tmp_path / "wal.db"
    engine = create_db_engine(db_path)
    init_db(db_path)
    with engine.connect() as conn:
        mode = conn.execute(text("PRAGMA journal_mode")).scalar_one()
        assert str(mode).lower() in {"wal", "delete", "truncate", "persist", "memory"}
        assert conn.execute(text("PRAGMA busy_timeout")).scalar_one() >= 5000
