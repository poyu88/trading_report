"""明細不得含合計列。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

from backend.domain.models import DetailRow
from backend.reports.detail_writer import write_detail_xlsx


def test_no_total_row(tmp_path: Path) -> None:
    rows = [
        DetailRow(
            buy_date=date(2025, 1, 1),
            sell_date=None,
            symbol="1111",
            name="測",
            trade_type_label="現股",
            buy_price=Decimal("1"),
            buy_qty=1,
            buy_commission=Decimal("0"),
            sell_price=None,
            sell_qty=None,
            sell_commission=None,
            sell_tax=None,
            interest=None,
            margin_amount=None,
            margin_annual_rate=None,
            cost=Decimal("1"),
            income=None,
            profit=None,
            profit_rate=None,
            actual_return_rate=None,
            broker="X",
            market_correlation=None,
            note=None,
        )
        for _ in range(10)
    ]
    path = write_detail_xlsx(rows, tmp_path)
    wb = load_workbook(path)
    ws = wb.active
    assert ws.max_row == 11  # 1 header + 10
    for r in range(1, 12):
        for c in range(1, 24):
            val = ws.cell(r, c).value
            if isinstance(val, str):
                assert "合計" not in val and "總合" not in val
            if isinstance(val, str) and val.startswith("="):
                raise AssertionError("不得有公式")


def test_empty_only_header(tmp_path: Path) -> None:
    path = write_detail_xlsx([], tmp_path)
    wb = load_workbook(path)
    ws = wb.active
    assert ws.max_row == 1
