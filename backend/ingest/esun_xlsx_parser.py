"""玉山證券真 XLSX：日期繼承、次列代號與結構重塑。"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from python_calamine import CalamineWorkbook

from backend.domain.exceptions import FileFormatError, ValidationError
from backend.ingest.html_parser import ParsedTable
from backend.ingest.mapping import MappingProfile, normalize_header

_TRADE_TYPES = frozenset({"現股買進", "現股賣出", "現沖買進", "現沖賣出"})
_COUNT_RE = re.compile(r"(\d+)\s*筆")


def normalize_esun_symbol(value: Any) -> str:
    """將玉山次列代號（可能為負數 float）正規化為正整數字串。"""
    if value is None:
        raise ValidationError("股票代號為空")
    if isinstance(value, bool):
        raise ValidationError(f"無法解析股票代號：{value!r}")
    if isinstance(value, (int, float, Decimal)):
        number = abs(Decimal(str(value)))
    else:
        text = str(value).strip().replace(",", "").replace("，", "")
        if text == "":
            raise ValidationError("股票代號為空")
        try:
            number = abs(Decimal(text))
        except InvalidOperation as exc:
            raise ValidationError(f"無法解析股票代號：{value!r}") from exc
    if number != number.to_integral_value():
        raise ValidationError(f"股票代號必須為整數：{value!r}")
    return str(int(number))


def _cell_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        # 避免 40.95 → 40.9500000001；整數 float 去小數
        as_dec = Decimal(str(value))
        if as_dec == as_dec.to_integral_value():
            return str(int(as_dec))
        return format(as_dec, "f")
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return str(int(value))
        return format(value, "f")
    return str(value).strip()


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _parse_date_cell(value: Any, formats: list[str]) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if _is_blank(value):
        return None
    text = str(value).strip()
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _row_is_date_banner(row: list[Any], formats: list[str]) -> date | None:
    if not row:
        return None
    parsed = _parse_date_cell(row[0], formats)
    if parsed is None:
        return None
    # 其餘儲存格皆空白才視為日期列
    for cell in row[1:]:
        if not _is_blank(cell):
            return None
    return parsed


def _row_trade_type(row: list[Any]) -> str | None:
    if not row or _is_blank(row[0]):
        return None
    text = str(row[0]).strip()
    if text in _TRADE_TYPES:
        return text
    return None


def _row_is_symbol_follow(row: list[Any]) -> bool:
    if not row:
        return False
    if not _is_blank(row[0]):
        return False
    if len(row) < 2 or _is_blank(row[1]):
        return False
    # 其餘業務欄應大致空白（允許空字串）
    for cell in row[2:]:
        if not _is_blank(cell):
            return False
    try:
        normalize_esun_symbol(row[1])
    except ValidationError:
        return False
    return True


def _row_is_subtotal(row: list[Any]) -> bool:
    if not row or _is_blank(row[0]):
        return False
    return "小計" in str(row[0])


def _find_header_row(data: list[list[Any]], profile: MappingProfile) -> int:
    required = set(profile.normalized_required)
    for idx, row in enumerate(data):
        headers = [normalize_header(_cell_str(c)) for c in row]
        if required.issubset(set(headers)):
            return idx
    raise FileFormatError(f"找不到玉山表頭（需含：{sorted(required)}）")


def _parse_footer_totals(row: list[Any]) -> dict[str, Any] | None:
    if not row or _is_blank(row[0]):
        return None
    if str(row[0]).strip() != "資料筆數":
        return None
    cells = [_cell_str(c) for c in row]
    declared = None
    if len(cells) > 1:
        match = _COUNT_RE.search(cells[1])
        if match:
            declared = int(match.group(1))

    def _pick(label: str) -> Decimal | None:
        for i, cell in enumerate(cells):
            if cell == label and i + 1 < len(cells):
                try:
                    return Decimal(cells[i + 1].replace(",", ""))
                except InvalidOperation:
                    return None
        return None

    return {
        "declared_count": declared,
        "gross_amount": _pick("成交價金"),
        "commission": _pick("手續費"),
        "tax": _pick("交易稅"),
        "net_settlement": _pick("淨收付金額"),
    }


def parse_esun_xlsx(path: Path, profile: MappingProfile, sheet_name: str | None = None) -> ParsedTable:
    try:
        workbook = CalamineWorkbook.from_path(str(path))
    except Exception as exc:
        raise FileFormatError(f"無法讀取玉山 Excel：{exc}") from exc

    names = workbook.sheet_names
    if not names:
        raise FileFormatError("Excel 沒有工作表")
    target = sheet_name or names[0]
    if target not in names:
        raise FileFormatError(f"找不到工作表：{target}")

    sheet = workbook.get_sheet_by_name(target)
    data = sheet.to_python(skip_empty_area=False)
    if not data:
        raise FileFormatError("工作表為空")

    header_idx = _find_header_row(data, profile)
    raw_headers = [normalize_header(_cell_str(c)) for c in data[header_idx]]
    # 扁平輸出表頭：原表頭 + 合成欄
    flat_headers = list(raw_headers)
    if "成交日" not in flat_headers:
        flat_headers.append("成交日")
    if "股票代號" not in flat_headers:
        flat_headers.append("股票代號")

    date_idx = flat_headers.index("成交日")
    symbol_idx = flat_headers.index("股票代號")
    side_idx = flat_headers.index("交易類別") if "交易類別" in flat_headers else 0
    name_idx = flat_headers.index("股票名稱") if "股票名稱" in flat_headers else 1
    gross_idx = flat_headers.index("成交價金") if "成交價金" in flat_headers else None
    commission_idx = flat_headers.index("手續費") if "手續費" in flat_headers else None
    tax_idx = flat_headers.index("交易稅") if "交易稅" in flat_headers else None

    current_date: date | None = None
    rows: list[tuple[int, list[str]]] = []
    footer: dict[str, Any] | None = None
    recognized_gross = Decimal(0)
    recognized_commission = Decimal(0)
    recognized_tax = Decimal(0)
    recognized_count = 0

    i = header_idx + 1
    while i < len(data):
        excel_row_number = i + 1  # 1-based
        row = list(data[i])
        # pad
        if len(row) < len(raw_headers):
            row += [None] * (len(raw_headers) - len(row))
        else:
            row = row[: len(raw_headers)]

        if all(_is_blank(c) for c in row):
            i += 1
            continue

        footer_candidate = _parse_footer_totals(row)
        if footer_candidate is not None:
            footer = footer_candidate
            i += 1
            continue

        first = _cell_str(row[0]) if row else ""
        if first.startswith("說明") or first.startswith("本功能"):
            i += 1
            continue

        if _row_is_subtotal(row):
            i += 1
            continue

        banner = _row_is_date_banner(row, profile.date_formats)
        if banner is not None:
            current_date = banner
            i += 1
            continue

        trade_type = _row_trade_type(row)
        if trade_type is not None:
            symbol = ""
            consume = 1
            if i + 1 < len(data) and _row_is_symbol_follow(list(data[i + 1])):
                symbol = normalize_esun_symbol(data[i + 1][1])
                consume = 2
            # 缺次列代號時留下空白 symbol，交由 normalizer 報錯

            values = [_cell_str(c) for c in row]
            while len(values) < len(flat_headers):
                values.append("")
            values[side_idx] = trade_type
            if name_idx < len(values):
                values[name_idx] = _cell_str(row[name_idx]) if name_idx < len(row) else ""
            values[date_idx] = current_date.isoformat() if current_date else ""
            values[symbol_idx] = symbol
            rows.append((excel_row_number, values[: len(flat_headers)]))

            recognized_count += 1
            if gross_idx is not None and gross_idx < len(row) and not _is_blank(row[gross_idx]):
                recognized_gross += Decimal(_cell_str(row[gross_idx]))
            if commission_idx is not None and commission_idx < len(row) and not _is_blank(
                row[commission_idx]
            ):
                recognized_commission += Decimal(_cell_str(row[commission_idx]))
            if tax_idx is not None and tax_idx < len(row) and not _is_blank(row[tax_idx]):
                recognized_tax += Decimal(_cell_str(row[tax_idx]))

            i += consume
            continue

        # 其他無法分類列略過（說明殘片等）
        i += 1

    reconciliation: dict[str, Any] | None = None
    if footer is not None:
        declared = footer.get("declared_count")
        fg = footer.get("gross_amount")
        fc = footer.get("commission")
        ft = footer.get("tax")
        matched = (
            declared == recognized_count
            and fg == recognized_gross
            and fc == recognized_commission
            and ft == recognized_tax
        )
        reconciliation = {
            "declared_count": declared,
            "recognized_count": recognized_count,
            "gross_amount": str(fg if fg is not None else recognized_gross),
            "commission": str(fc if fc is not None else recognized_commission),
            "tax": str(ft if ft is not None else recognized_tax),
            "net_settlement": (
                str(footer["net_settlement"]) if footer.get("net_settlement") is not None else None
            ),
            "matched": bool(matched),
        }
    else:
        reconciliation = {
            "declared_count": None,
            "recognized_count": recognized_count,
            "gross_amount": str(recognized_gross),
            "commission": str(recognized_commission),
            "tax": str(recognized_tax),
            "net_settlement": None,
            "matched": False,
        }

    return ParsedTable(
        headers=flat_headers,
        rows=rows,
        sheet_name=target,
        source_reconciliation=reconciliation,
    )
