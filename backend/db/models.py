"""SQLAlchemy ORM 模型。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Broker(Base):
    __tablename__ = "brokers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)

    accounts: Mapped[list[Account]] = relationship(back_populates="broker")


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("broker_id", "account_label", name="uq_broker_account"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    broker_id: Mapped[str] = mapped_column(ForeignKey("brokers.id"), nullable=False)
    account_label: Mapped[str] = mapped_column(String(128), nullable=False)

    broker: Mapped[Broker] = relationship(back_populates="accounts")
    batches: Mapped[list[ImportBatch]] = relationship(back_populates="account")
    trades: Mapped[list[TradeRow]] = relationship(back_populates="account")


class ImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        UniqueConstraint("account_id", "file_sha256", "profile_id", "profile_version", name="uq_batch_file"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    profile_id: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    imported_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    archive_path: Mapped[str | None] = mapped_column(String(1024))

    account: Mapped[Account] = relationship(back_populates="batches")
    raw_rows: Mapped[list[RawRow]] = relationship(back_populates="batch")


class RawRow(Base):
    __tablename__ = "raw_rows"
    __table_args__ = (
        UniqueConstraint("batch_id", "sheet_name", "row_index", name="uq_raw_coord"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id"), nullable=False)
    sheet_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_json: Mapped[str] = mapped_column(Text, nullable=False)
    row_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    parse_status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))

    batch: Mapped[ImportBatch] = relationship(back_populates="raw_rows")
    trade: Mapped[TradeRow | None] = relationship(back_populates="raw_row", uselist=False)


class TradeRow(Base):
    __tablename__ = "trades"
    __table_args__ = (
        CheckConstraint("side IN ('BUY','SELL')", name="ck_trade_side"),
        CheckConstraint("trade_type IN ('CASH', 'DAY_TRADE')", name="ck_trade_type"),
        CheckConstraint("quantity > 0", name="ck_trade_qty"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    raw_row_id: Mapped[str] = mapped_column(ForeignKey("raw_rows.id"), unique=True, nullable=False)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str | None] = mapped_column(String(128))
    trade_date: Mapped[str] = mapped_column(String(10), nullable=False)
    trade_time: Mapped[str | None] = mapped_column(String(16))
    trade_sequence: Mapped[int | None] = mapped_column(Integer)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    trade_type: Mapped[str] = mapped_column(String(16), nullable=False, default="CASH")
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_txt: Mapped[str] = mapped_column(Text, nullable=False)
    gross_amount_txt: Mapped[str] = mapped_column(Text, nullable=False)
    commission_txt: Mapped[str] = mapped_column(Text, nullable=False)
    tax_txt: Mapped[str] = mapped_column(Text, nullable=False)
    interest_txt: Mapped[str] = mapped_column(Text, nullable=False, default="0")
    net_settlement_txt: Mapped[str | None] = mapped_column(Text)
    external_trade_id: Mapped[str | None] = mapped_column(String(128))
    raw_payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    raw_row: Mapped[RawRow] = relationship(back_populates="trade")
    account: Mapped[Account] = relationship(back_populates="trades")


class OpeningLotRow(Base):
    __tablename__ = "opening_lots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    buy_date: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_cost_txt: Mapped[str] = mapped_column(Text, nullable=False)
    approval_note: Mapped[str] = mapped_column(Text, nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="approved")


class AllocationRun(Base):
    __tablename__ = "allocation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"))

    allocations: Mapped[list[FifoAllocation]] = relationship(back_populates="run")
    issues: Mapped[list[ReconciliationIssueRow]] = relationship(back_populates="run")


class FifoAllocation(Base):
    __tablename__ = "fifo_allocations"
    __table_args__ = (
        CheckConstraint("allocated_quantity > 0", name="ck_alloc_qty"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("allocation_runs.id"), nullable=False)
    buy_trade_id: Mapped[str | None] = mapped_column(ForeignKey("trades.id"))
    opening_lot_id: Mapped[str | None] = mapped_column(ForeignKey("opening_lots.id"))
    sell_trade_id: Mapped[str] = mapped_column(ForeignKey("trades.id"), nullable=False)
    allocated_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)

    run: Mapped[AllocationRun] = relationship(back_populates="allocations")


class ReconciliationIssueRow(Base):
    __tablename__ = "reconciliation_issues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("allocation_runs.id"))
    batch_id: Mapped[str | None] = mapped_column(ForeignKey("import_batches.id"))
    trade_id: Mapped[str | None] = mapped_column(ForeignKey("trades.id"))
    issue_code: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    detail_json: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    run: Mapped[AllocationRun | None] = relationship(back_populates="issues")


class ReportRun(Base):
    __tablename__ = "report_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    allocation_run_id: Mapped[str] = mapped_column(ForeignKey("allocation_runs.id"), nullable=False)
    report_type: Mapped[str] = mapped_column(String(32), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
