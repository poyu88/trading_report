"""領域資料結構（Decimal 精確運算）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal
from typing import Any, Literal

Side = Literal["BUY", "SELL"]
TradeType = Literal["CASH", "DAY_TRADE"]


def decimal_to_txt(value: Decimal) -> str:
    """將 Decimal 轉成規範化十進位字串。"""
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text if text else "0"


def txt_to_decimal(value: str) -> Decimal:
    """從十進位字串還原 Decimal。"""
    return Decimal(value)


@dataclass(frozen=True)
class Trade:
    trade_id: str
    account_id: str
    source_row_id: str
    symbol: str
    name: str | None
    trade_date: date
    trade_time: time | None
    trade_sequence: int | None
    side: Side
    trade_type: TradeType
    currency: str
    quantity: int
    unit_price: Decimal
    gross_amount: Decimal
    commission: Decimal
    tax: Decimal
    interest: Decimal
    net_settlement: Decimal | None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OpeningLot:
    lot_id: str
    account_id: str
    symbol: str
    currency: str
    buy_date: date
    quantity: int
    unit_cost: Decimal
    approval_note: str
    source_reference: str | None = None


@dataclass(frozen=True)
class Allocation:
    run_id: str
    allocation_id: str
    buy_trade_id: str | None
    opening_lot_id: str | None
    sell_trade_id: str
    quantity: int
    sequence_no: int
    match_type: str = "STANDARD_FIFO"


@dataclass
class LotRemaining:
    buy_trade_id: str | None
    opening_lot_id: str | None
    available: int
    trade_date: date
    unit_price: Decimal
    provenance_order: int


@dataclass(frozen=True)
class ReconciliationIssue:
    issue_code: str
    severity: str
    detail: dict[str, Any]
    trade_id: str | None = None
    batch_id: str | None = None


@dataclass(frozen=True)
class DetailRow:
    buy_date: date
    sell_date: date | None
    symbol: str
    name: str | None
    trade_type_label: str
    buy_price: Decimal
    buy_qty: int
    buy_commission: Decimal
    sell_price: Decimal | None
    sell_qty: int | None
    sell_commission: Decimal | None
    sell_tax: Decimal | None
    interest: Decimal | None
    margin_amount: Decimal | None
    margin_annual_rate: Decimal | None
    cost: Decimal
    income: Decimal | None
    profit: Decimal | None
    profit_rate: Decimal | None
    actual_return_rate: Decimal | None
    broker: str
    market_correlation: Decimal | None
    note: str | None
    # 稽核用（不寫入 A～W）
    buy_trade_id: str | None = None
    sell_trade_id: str | None = None
    opening_lot_id: str | None = None
    allocation_id: str | None = None
