"""以 openpyxl 新建純明細 XLSX。"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from backend.domain.models import DetailRow
from backend.reports.field_schema import HEADERS


def _safe_text(value: str | None) -> str | None:
    if value is None:
        return None
    if value and value[0] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def unique_output_path(path: Path) -> Path:
    """若路徑已存在則附加 _01、_02…，避免覆寫。"""
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for i in range(1, 1000):
        candidate = parent / f"{stem}_{i:02d}{suffix}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"無法產生唯一檔名：{path}")


# 向後相容別名
_unique_path = unique_output_path


def write_detail_xlsx(
    rows: list[DetailRow],
    output_dir: Path,
    *,
    draft: bool = False,
    when: datetime | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = (when or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
    prefix = "交易明細_DRAFT_" if draft else "交易明細_"
    final_path = _unique_path(output_dir / f"{prefix}{stamp}.xlsx")
    tmp_path = final_path.with_suffix(".tmp.xlsx")

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "交易明細"

    for col, header in enumerate(HEADERS, start=1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True)

    for r_idx, row in enumerate(rows, start=2):
        _write_row(ws, r_idx, row)

    ws.auto_filter.ref = f"A1:W{max(1, len(rows) + 1)}"
    ws.freeze_panes = "A2"
    _set_column_widths(ws)

    wb.save(tmp_path)
    # 驗證後改名
    _validate_workbook(tmp_path, expected_rows=len(rows))
    tmp_path.replace(final_path)
    return final_path


def _write_row(ws: Worksheet, r_idx: int, row: DetailRow) -> None:
    values: list[object | None] = [
        row.buy_date,
        row.sell_date,
        _safe_text(row.symbol),
        _safe_text(row.name),
        _safe_text(row.trade_type_label),
        float(row.buy_price),
        int(row.buy_qty),
        float(row.buy_commission),
        float(row.sell_price) if row.sell_price is not None else None,
        int(row.sell_qty) if row.sell_qty is not None else None,
        float(row.sell_commission) if row.sell_commission is not None else None,
        float(row.sell_tax) if row.sell_tax is not None else None,
        float(row.interest) if row.interest is not None else None,
        float(row.margin_amount) if row.margin_amount is not None else None,
        float(row.margin_annual_rate) if row.margin_annual_rate is not None else None,
        float(row.cost),
        float(row.income) if row.income is not None else None,
        float(row.profit) if row.profit is not None else None,
        float(row.profit_rate) if row.profit_rate is not None else None,
        float(row.actual_return_rate) if row.actual_return_rate is not None else None,
        _safe_text(row.broker),
        float(row.market_correlation) if row.market_correlation is not None else None,
        _safe_text(row.note),
    ]
    for c_idx, value in enumerate(values, start=1):
        cell = ws.cell(row=r_idx, column=c_idx, value=value)
        if c_idx in (1, 2) and isinstance(value, date):
            cell.number_format = "yyyy-mm-dd"
        if c_idx == 3:
            cell.number_format = "@"
        if c_idx in (6, 8, 9, 11, 12, 13, 14, 15, 16, 17, 18) and value is not None:
            cell.number_format = "#,##0.00"
        if c_idx in (19, 20) and value is not None:
            cell.number_format = "0.00%"


def _set_column_widths(ws: Worksheet) -> None:
    widths = [12, 12, 10, 12, 8, 10, 10, 10, 10, 10, 10, 10, 8, 10, 10, 12, 12, 10, 10, 10, 10, 10, 16]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _validate_workbook(path: Path, expected_rows: int) -> None:
    from openpyxl import load_workbook

    wb = load_workbook(path, data_only=False)
    ws = wb.active
    assert ws is not None
    headers = [ws.cell(1, c).value for c in range(1, 24)]
    if headers != HEADERS:
        raise ValueError(f"表頭不符：{headers}")
    max_row = ws.max_row or 1
    if max_row != expected_rows + 1:
        raise ValueError(f"列數不符：期望 {expected_rows + 1}，實際 {max_row}")
    # 不得有公式
    for row in ws.iter_rows(min_row=1, max_row=max_row, max_col=23):
        for cell in row:
            if (
                isinstance(cell.value, str)
                and cell.value.startswith("=")
                and not cell.value.startswith("'")
            ):
                raise ValueError(f"禁止公式：{cell.coordinate}={cell.value}")
    # 不得有合計列關鍵字
    for r in range(2, max_row + 1):
        for c in range(1, 24):
            val = ws.cell(r, c).value
            if isinstance(val, str) and re.search(r"總合|合計|小計", val):
                raise ValueError(f"禁止合計列文字：{val}")
