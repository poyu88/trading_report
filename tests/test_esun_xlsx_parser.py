"""ING-05/06/07、NORM-04：玉山 XLSX 結構解析（合成測資）。"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from backend.ingest.mapping import load_profile
from tests.esun_xlsx_fixtures import (
    write_esun_missing_symbol_row,
    write_esun_trade_without_date,
    write_esun_with_unsupported_trade_type,
    write_synthetic_esun_xlsx,
)


def test_esun_profile_exists() -> None:
    profile = load_profile("esun_xlsx_v1")
    assert profile.profile_id == "esun_xlsx_v1"
    assert profile.source_format == "esun_xlsx"


def test_parse_inherits_date_and_next_row_symbol(tmp_path: Path) -> None:
    from backend.ingest.esun_xlsx_parser import parse_esun_xlsx
    from backend.services.import_service import preview_import

    path = write_synthetic_esun_xlsx(tmp_path / "esun_synth.xlsx")
    profile = load_profile("esun_xlsx_v1")
    table = parse_esun_xlsx(path, profile)

    assert "成交日" in table.headers
    assert "股票代號" in table.headers

    preview = preview_import(path, "esun_xlsx_v1")
    ok = [r for r in preview.rows if r.status == "ok"]
    assert len(ok) == 5  # 現股 3 + 現沖 2
    symbols = {r.symbol for r in ok}
    assert symbols == {"4971", "3162"}
    assert all("." not in (r.symbol or "") for r in ok)
    assert all("e" not in (r.symbol or "").lower() for r in ok)


def test_four_trade_types_recognized_and_subtotals_excluded(tmp_path: Path) -> None:
    from backend.services.import_service import preview_import

    path = write_synthetic_esun_xlsx(tmp_path / "esun_types.xlsx")
    preview = preview_import(path, "esun_xlsx_v1")

    assert preview.file_kind == "xlsx"
    assert preview.trade_count == 5
    assert preview.buy_count == 3
    assert preview.sell_count == 2
    assert preview.error_count == 0
    assert all(r.status == "ok" for r in preview.rows)


def test_negative_symbol_normalized_to_text() -> None:
    from backend.ingest.esun_xlsx_parser import normalize_esun_symbol

    assert normalize_esun_symbol(-4971.0) == "4971"
    assert normalize_esun_symbol("-3162") == "3162"
    assert normalize_esun_symbol(Decimal("-8927.0")) == "8927"


def test_missing_symbol_row_is_error(tmp_path: Path) -> None:
    from backend.services.import_service import preview_import

    path = write_esun_missing_symbol_row(tmp_path / "esun_nosym.xlsx")
    preview = preview_import(path, "esun_xlsx_v1")
    assert preview.trade_count == 0
    assert preview.error_count >= 1


def test_trade_before_date_banner_is_error(tmp_path: Path) -> None:
    from backend.services.import_service import preview_import

    path = write_esun_trade_without_date(tmp_path / "esun_nodate.xlsx")
    preview = preview_import(path, "esun_xlsx_v1")
    assert preview.trade_count == 0
    assert preview.error_count >= 1


def test_unsupported_trade_type_becomes_exception_not_silent_drop(tmp_path: Path) -> None:
    """NORM-03／FR-02：融資等未支援類型須進例外，不得靜默丟棄。"""
    from backend.services.import_service import preview_import

    path = write_esun_with_unsupported_trade_type(tmp_path / "esun_margin.xlsx")
    preview = preview_import(path, "esun_xlsx_v1")

    assert preview.trade_count == 1
    assert preview.error_count == 1
    errors = [r for r in preview.rows if r.status == "error"]
    assert len(errors) == 1
    assert errors[0].symbol == "3162"
    assert errors[0].message is not None
    assert "UNSUPPORTED_TRADE_TYPE" in errors[0].message or "未支援" in errors[0].message
    ok = [r for r in preview.rows if r.status == "ok"]
    assert len(ok) == 1
    assert ok[0].symbol == "3162"
    assert ok[0].side == "BUY"
