"""將映射後的原始欄位正規化為 canonical 交易。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.domain.exceptions import ValidationError
from backend.ingest.mapping import MappingProfile


@dataclass
class NormalizedCandidate:
    symbol: str
    name: str | None
    trade_date: date
    side: str
    trade_type: str
    currency: str
    quantity: int
    unit_price: Decimal
    gross_amount: Decimal
    commission: Decimal
    tax: Decimal
    interest: Decimal
    net_settlement: Decimal | None
    raw: dict[str, Any]
    excluded: bool = False
    exclude_reason: str | None = None
    error_code: str | None = None
    error_message: str | None = None


_SYMBOL_NAME_RE = re.compile(r"^\s*([A-Za-z0-9]+)\s+(.+?)\s*$")


def parse_decimal(text: str, field_name: str) -> Decimal:
    cleaned = text.strip().replace(",", "").replace("，", "")
    if cleaned == "":
        return Decimal(0)
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValidationError(f"{field_name} 不是合法數字：{text!r}") from exc


def parse_quantity(text: str) -> int:
    value = parse_decimal(text, "成交股數")
    if value != value.to_integral_value() or value <= 0:
        raise ValidationError(f"成交股數必須為正整數：{text!r}")
    return int(value)


def parse_trade_date(text: str, formats: list[str]) -> date:
    raw = text.strip()
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValidationError(f"無法解析成交日：{text!r}")


def split_symbol_and_name(text: str) -> tuple[str, str | None]:
    raw = text.strip()
    match = _SYMBOL_NAME_RE.match(raw)
    if match:
        return match.group(1), match.group(2)
    # 只有代號
    if re.fullmatch(r"[A-Za-z0-9]+", raw):
        return raw, None
    raise ValidationError(f"無法拆解商品欄：{text!r}")


def should_exclude(first_cell: str, profile: MappingProfile) -> str | None:
    text = first_cell.strip()
    for prefix in profile.exclude_row_prefixes:
        if text.startswith(prefix):
            return f"排除列：{prefix}"
    return None


def normalize_mapped_row(
    mapped: dict[str, str],
    profile: MappingProfile,
    original_cells: dict[str, str],
) -> NormalizedCandidate:
    first_value = next(iter(original_cells.values()), "")
    exclude_reason = should_exclude(first_value, profile)
    if exclude_reason:
        return NormalizedCandidate(
            symbol="",
            name=None,
            trade_date=date.min,
            side="",
            trade_type="CASH",
            currency="",
            quantity=0,
            unit_price=Decimal(0),
            gross_amount=Decimal(0),
            commission=Decimal(0),
            tax=Decimal(0),
            interest=Decimal(0),
            net_settlement=None,
            raw=dict(original_cells),
            excluded=True,
            exclude_reason=exclude_reason,
        )

    try:
        symbol_src = mapped.get("symbol_and_name") or mapped.get("symbol") or ""
        if "symbol_and_name" in mapped:
            symbol, name = split_symbol_and_name(symbol_src)
        else:
            symbol = symbol_src.strip()
            name = mapped.get("name")
            if not symbol:
                raise ValidationError("缺少股票代號")

        side_raw = mapped.get("side_raw", "").strip()
        side = profile.side_map.get(side_raw)
        if side not in ("BUY", "SELL"):
            return NormalizedCandidate(
                symbol=symbol,
                name=name,
                trade_date=date.min,
                side="",
                trade_type="CASH",
                currency="",
                quantity=0,
                unit_price=Decimal(0),
                gross_amount=Decimal(0),
                commission=Decimal(0),
                tax=Decimal(0),
                interest=Decimal(0),
                net_settlement=None,
                raw=dict(original_cells),
                error_code="UNSUPPORTED_TRADE_TYPE",
                error_message=f"未支援買賣別：{side_raw!r}",
            )

        currency_raw = mapped.get("currency_raw", "").strip()
        currency = profile.currency_map.get(currency_raw)
        if not currency:
            raise ValidationError(f"未知幣別：{currency_raw!r}")

        trade_date = parse_trade_date(mapped.get("trade_date", ""), profile.date_formats)
        quantity = parse_quantity(mapped.get("quantity", ""))
        unit_price = parse_decimal(mapped.get("unit_price", ""), "成交價")
        if unit_price <= 0:
            raise ValidationError(f"成交價必須 > 0：{unit_price}")
        gross_amount = parse_decimal(mapped.get("gross_amount", ""), "成交金額")
        commission = parse_decimal(mapped.get("commission", "0"), "手續費")
        tax = parse_decimal(mapped.get("tax", "0"), "交易稅")
        interest = parse_decimal(mapped.get("interest", "0"), "利息")
        net_raw = mapped.get("net_settlement")
        net_settlement = parse_decimal(net_raw, "淨收付") if net_raw not in (None, "") else None

        if commission < 0 or tax < 0 or interest < 0 or gross_amount < 0:
            raise ValidationError("金額／費用不得為負")

        return NormalizedCandidate(
            symbol=symbol,
            name=name,
            trade_date=trade_date,
            side=side,
            trade_type="CASH",
            currency=currency,
            quantity=quantity,
            unit_price=unit_price,
            gross_amount=gross_amount,
            commission=commission,
            tax=tax,
            interest=interest,
            net_settlement=net_settlement,
            raw=dict(original_cells),
        )
    except ValidationError as exc:
        return NormalizedCandidate(
            symbol="",
            name=None,
            trade_date=date.min,
            side="",
            trade_type="CASH",
            currency="",
            quantity=0,
            unit_price=Decimal(0),
            gross_amount=Decimal(0),
            commission=Decimal(0),
            tax=Decimal(0),
            interest=Decimal(0),
            net_settlement=None,
            raw=dict(original_cells),
            error_code="VALIDATION_ERROR",
            error_message=str(exc),
        )
