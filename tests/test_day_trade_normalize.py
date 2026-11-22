"""NORM-05：現沖 BUY／SELL 正規化與費用保留。"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from backend.db.models import TradeRow
from backend.ingest.mapping import load_profile
from backend.ingest.normalizer import normalize_mapped_row
from backend.services.import_service import apply_import, preview_import
from tests.esun_xlsx_fixtures import write_synthetic_esun_xlsx


def test_day_trade_buy_and_sell_normalize_with_fees() -> None:
    profile = load_profile("esun_xlsx_v1")
    assert profile.trade_type_map.get("現沖買進") == "DAY_TRADE"
    assert profile.trade_type_map.get("現沖賣出") == "DAY_TRADE"

    buy = normalize_mapped_row(
        {
            "side_raw": "現沖買進",
            "name": "精確",
            "symbol": "3162",
            "trade_date": "2025-02-25",
            "quantity": "1000",
            "unit_price": "50.5",
            "gross_amount": "50500",
            "commission": "71",
            "tax": "0",
            "net_settlement": "-50571",
        },
        profile,
        {"交易類別": "現沖買進"},
    )
    assert buy.error_code is None
    assert buy.excluded is False
    assert buy.side == "BUY"
    assert buy.trade_type == "DAY_TRADE"
    assert buy.quantity == 1000
    assert buy.unit_price == Decimal("50.5")
    assert buy.gross_amount == Decimal(50500)
    assert buy.commission == Decimal(71)
    assert buy.tax == Decimal(0)

    sell = normalize_mapped_row(
        {
            "side_raw": "現沖賣出",
            "name": "精確",
            "symbol": "3162",
            "trade_date": "2025-02-25",
            "quantity": "1000",
            "unit_price": "52.4",
            "gross_amount": "52400",
            "commission": "74",
            "tax": "78",
            "net_settlement": "52248",
        },
        profile,
        {"交易類別": "現沖賣出"},
    )
    assert sell.error_code is None
    assert sell.side == "SELL"
    assert sell.trade_type == "DAY_TRADE"
    assert sell.commission == Decimal(74)
    assert sell.tax == Decimal(78)


def test_unknown_trade_type_still_errors() -> None:
    profile = load_profile("esun_xlsx_v1")
    cand = normalize_mapped_row(
        {
            "side_raw": "融資買進",
            "name": "精確",
            "symbol": "3162",
            "trade_date": "2025-02-25",
            "quantity": "1000",
            "unit_price": "50",
            "gross_amount": "50000",
            "commission": "10",
            "tax": "0",
        },
        profile,
        {"交易類別": "融資買進"},
    )
    assert cand.error_code in ("UNSUPPORTED_TRADE_TYPE", "DAY_TRADE_UNSUPPORTED") or (
        cand.error_code is not None
    )
    assert cand.error_code != ""
    assert cand.side == "" or cand.error_code is not None


def test_esun_preview_all_five_trades_ok_including_day_trade(tmp_path: Path) -> None:
    path = write_synthetic_esun_xlsx(tmp_path / "esun_day.xlsx")
    preview = preview_import(path, "esun_xlsx_v1")
    assert preview.trade_count == 5
    assert preview.error_count == 0
    assert preview.buy_count == 3  # 2 現股買 + 1 現沖買
    assert preview.sell_count == 2  # 1 現股賣 + 1 現沖賣


def test_apply_imports_day_trade_rows(tmp_path: Path, db_session) -> None:
    path = write_synthetic_esun_xlsx(tmp_path / "esun_apply_day.xlsx")
    result = apply_import(db_session, path, "玉山", "main", "esun_xlsx_v1")
    db_session.commit()
    assert result.trade_count == 5
    assert result.error_count == 0
    trades = list(db_session.scalars(select(TradeRow)).all())
    assert len(trades) == 5
    day = [t for t in trades if t.trade_type == "DAY_TRADE"]
    cash = [t for t in trades if t.trade_type == "CASH"]
    assert len(day) == 2
    assert len(cash) == 3
    assert {t.side for t in day} == {"BUY", "SELL"}
    assert all(t.commission_txt for t in day)
