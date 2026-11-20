"""常用查詢與寫入輔助。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Account, AllocationRun, Broker, ImportBatch, TradeRow


def get_or_create_broker(session: Session, broker_id: str, name: str) -> Broker:
    broker = session.get(Broker, broker_id)
    if broker:
        return broker
    existing = session.scalar(select(Broker).where(Broker.name == name))
    if existing:
        return existing
    broker = Broker(id=broker_id, name=name)
    session.add(broker)
    session.flush()
    return broker


def get_or_create_account(
    session: Session,
    account_id: str,
    broker_id: str,
    account_label: str,
) -> Account:
    account = session.get(Account, account_id)
    if account:
        return account
    existing = session.scalar(
        select(Account).where(
            Account.broker_id == broker_id,
            Account.account_label == account_label,
        )
    )
    if existing:
        return existing
    account = Account(id=account_id, broker_id=broker_id, account_label=account_label)
    session.add(account)
    session.flush()
    return account


def find_batch_by_hash(
    session: Session,
    account_id: str,
    file_sha256: str,
    profile_id: str,
    profile_version: int,
) -> ImportBatch | None:
    return session.scalar(
        select(ImportBatch).where(
            ImportBatch.account_id == account_id,
            ImportBatch.file_sha256 == file_sha256,
            ImportBatch.profile_id == profile_id,
            ImportBatch.profile_version == profile_version,
        )
    )


def list_trades_for_account(session: Session, account_id: str) -> list[TradeRow]:
    return list(
        session.scalars(
            select(TradeRow)
            .where(TradeRow.account_id == account_id)
            .order_by(TradeRow.trade_date, TradeRow.trade_sequence, TradeRow.id)
        )
    )


def latest_allocation_run(session: Session, account_id: str) -> AllocationRun | None:
    return session.scalar(
        select(AllocationRun)
        .where(AllocationRun.account_id == account_id)
        .order_by(AllocationRun.started_at_utc.desc())
        .limit(1)
    )


def find_account_by_label(session: Session, account_label: str) -> Account | None:
    return session.scalar(select(Account).where(Account.account_label == account_label))
