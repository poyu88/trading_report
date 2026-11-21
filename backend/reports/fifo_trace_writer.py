"""輸出 FIFO 配對及未配對明細 XLSX。"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from backend.reports.detail_projector import FifoTraceRow
from backend.reports.detail_writer import unique_output_path

HEADERS = [
    "列語意",
    "股票代號",
    "商品名稱",
    "類別",
    "買入日期",
    "賣出日期",
    "股數",
    "單價",
    "成交價金",
    "手續費",
    "交易稅",
    "利息",
    "成本",
    "收入",
    "損益",
    "buy_trade_id",
    "sell_trade_id",
    "allocation_id",
    "券商",
    "備註",
]


def write_fifo_trace_xlsx(
    rows: list[FifoTraceRow],
    output_dir: Path,
    *,
    when: datetime | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = (when or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
    final_path = unique_output_path(output_dir / f"FIFO配對及未配對明細_{stamp}.xlsx")
    tmp_path = final_path.with_suffix(".tmp.xlsx")

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "FIFO配對及未配對"

    for col, header in enumerate(HEADERS, start=1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True)

    for r_idx, row in enumerate(rows, start=2):
        values: list[object | None] = [
            row.row_kind,
            row.symbol,
            row.name,
            row.trade_type_label,
            row.buy_date,
            row.sell_date,
            int(row.quantity),
            float(row.unit_price) if row.unit_price is not None else None,
            float(row.gross_amount) if row.gross_amount is not None else None,
            float(row.commission) if row.commission is not None else None,
            float(row.tax) if row.tax is not None else None,
            float(row.interest) if row.interest is not None else None,
            float(row.cost) if row.cost is not None else None,
            float(row.income) if row.income is not None else None,
            float(row.profit) if row.profit is not None else None,
            row.buy_trade_id,
            row.sell_trade_id,
            row.allocation_id,
            row.broker,
            row.note,
        ]
        for c_idx, value in enumerate(values, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=value)
            if c_idx in (5, 6) and isinstance(value, date):
                cell.number_format = "yyyy-mm-dd"
            if c_idx == 2:
                cell.number_format = "@"

    for i, w in enumerate([14, 10, 12, 8, 12, 12, 10, 10, 12, 10, 10, 8, 12, 12, 10, 36, 36, 36, 10, 40], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:T{max(1, len(rows) + 1)}"

    wb.save(tmp_path)
    tmp_path.replace(final_path)
    return final_path
