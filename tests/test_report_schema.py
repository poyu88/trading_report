"""報表 schema／型別。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

from backend.domain.models import DetailRow
from backend.reports.detail_writer import write_detail_xlsx
from backend.reports.field_schema import HEADERS


def _sample_rows() -> list[DetailRow]:
    return [
        DetailRow(
            buy_date=date(2025, 1, 1),
            sell_date=date(2025, 2, 1),
            symbol="00685L",
            name="測試",
            trade_type_label="現股",
            buy_price=Decimal(10),
            buy_qty=100,
            buy_commission=Decimal(20),
            sell_price=Decimal(12),
            sell_qty=100,
            sell_commission=Decimal(18),
            sell_tax=Decimal(36),
            interest=None,
            margin_amount=None,
            margin_annual_rate=None,
            cost=Decimal(1020),
            income=Decimal(1146),
            profit=Decimal(126),
            profit_rate=Decimal("0.1235"),
            actual_return_rate=None,
            broker="群益",
            market_correlation=None,
            note=None,
        ),
        DetailRow(
            buy_date=date(2025, 3, 1),
            sell_date=None,
            symbol="2330",
            name="台積電",
            trade_type_label="現股",
            buy_price=Decimal(500),
            buy_qty=10,
            buy_commission=Decimal(0),
            sell_price=None,
            sell_qty=None,
            sell_commission=None,
            sell_tax=None,
            interest=None,
            margin_amount=None,
            margin_annual_rate=None,
            cost=Decimal(5000),
            income=None,
            profit=None,
            profit_rate=None,
            actual_return_rate=None,
            broker="群益",
            market_correlation=None,
            note=None,
        ),
    ]


def test_headers_and_types(tmp_path: Path) -> None:
    path = write_detail_xlsx(_sample_rows(), tmp_path)
    wb = load_workbook(path)
    ws = wb.active
    assert [ws.cell(1, c).value for c in range(1, 24)] == HEADERS
    assert ws.max_row == 3
    # 股票代號為文字
    assert ws.cell(2, 3).value == "00685L"
    # 未賣出欄位為空
    assert ws.cell(3, 2).value is None
    assert ws.cell(3, 9).value is None
    assert ws.cell(3, 18).value is None
    # 數值型
    assert isinstance(ws.cell(2, 6).value, (int, float))
    assert isinstance(ws.cell(2, 7).value, int)
