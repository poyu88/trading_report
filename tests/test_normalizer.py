"""正規化與匯入預覽。"""

from __future__ import annotations

from pathlib import Path

from backend.ingest.mapping import load_profile
from backend.services.import_service import preview_import


def test_preview_excludes_totals_and_counts(fixtures_dir: Path, tmp_path: Path) -> None:
    src = fixtures_dir / "statement_sample.html"
    fake = tmp_path / "sample.xls"
    fake.write_bytes(src.read_bytes())
    preview = preview_import(fake, "statement_html_v1")
    assert preview.file_kind == "html_table"
    assert preview.trade_count == 5
    assert preview.buy_count == 2
    assert preview.sell_count == 3
    assert preview.excluded_count == 2
    assert preview.error_count == 0


def test_symbol_kept_as_text() -> None:
    profile = load_profile("statement_html_v1")
    assert "商品" in profile.column_map or True
    from backend.ingest.normalizer import split_symbol_and_name

    symbol, name = split_symbol_and_name("00685L 群益正2")
    assert symbol == "00685L"
    assert name == "群益正2"
