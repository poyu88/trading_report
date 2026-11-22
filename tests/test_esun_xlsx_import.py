"""ING-08、現沖邊界、來源核對與結構失敗 rollback（合成測資）。"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook
from sqlalchemy import func, select

from backend.db.models import TradeRow
from backend.db.session import init_db, make_session_factory
from backend.domain.exceptions import FileFormatError, ProfileError
from backend.services.import_service import apply_import, preview_import
from tests.esun_xlsx_fixtures import write_synthetic_esun_xlsx


def test_preview_source_totals_reconcile(tmp_path: Path) -> None:
    path = write_synthetic_esun_xlsx(tmp_path / "esun_recon.xlsx")
    preview = preview_import(path, "esun_xlsx_v1")

    # 來源辨識 5 筆（含現沖）全部通過類型驗證
    assert preview.trade_count == 5
    assert preview.error_count == 0

    recon = getattr(preview, "source_reconciliation", None)
    assert recon is not None
    assert recon["declared_count"] == 5
    assert recon["recognized_count"] == 5
    assert Decimal(str(recon["gross_amount"])) == Decimal(266900)
    assert Decimal(str(recon["commission"])) == Decimal(377)
    assert Decimal(str(recon["tax"])) == Decimal(180)
    assert recon["matched"] is True


def test_apply_imports_cash_and_day_trade(tmp_path: Path, db_session) -> None:
    path = write_synthetic_esun_xlsx(tmp_path / "esun_apply.xlsx")
    result = apply_import(db_session, path, "玉山", "main", "esun_xlsx_v1")
    db_session.commit()

    assert result.trade_count == 5
    assert result.error_count == 0
    assert result.already_imported is False

    trades = list(db_session.scalars(select(TradeRow)).all())
    assert len(trades) == 5
    assert {t.trade_type for t in trades} == {"CASH", "DAY_TRADE"}
    assert {t.symbol for t in trades} == {"4971", "3162"}
    buy_qty = sum(t.quantity for t in trades if t.side == "BUY")
    sell_qty = sum(t.quantity for t in trades if t.side == "SELL")
    assert buy_qty == 3000  # 2000 現股 + 1000 現沖
    assert sell_qty == 1300  # 300 現股 + 1000 現沖


def test_structural_failure_rolls_back_without_trades(tmp_path: Path) -> None:
    """找不到玉山表頭時，apply 不得寫入任何 trades。"""
    bad = tmp_path / "not_esun.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["不是玉山表頭", "A", "B"])
    ws.append(["x", 1, 2])
    wb.save(bad)

    db_path = tmp_path / "rollback.db"
    engine = init_db(db_path)
    Session = make_session_factory(engine)
    session = Session()
    try:
        with pytest.raises((FileFormatError, ProfileError, ValueError)):
            apply_import(session, bad, "玉山", "main", "esun_xlsx_v1")
        session.rollback()
    finally:
        count = session.scalar(select(func.count()).select_from(TradeRow)) or 0
        session.close()
    assert count == 0
