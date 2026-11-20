"""ING：格式偵測。"""

from __future__ import annotations

from pathlib import Path

from backend.ingest.detector import FileKind, detect_file


def test_detect_html_pseudo_xls(fixtures_dir: Path, tmp_path: Path) -> None:
    src = fixtures_dir / "statement_sample.html"
    fake = tmp_path / "Statement.xls"
    fake.write_bytes(src.read_bytes())
    detected = detect_file(fake)
    assert detected.kind == FileKind.HTML_TABLE


def test_detect_csv_utf8(tmp_path: Path) -> None:
    path = tmp_path / "a.csv"
    path.write_text("商品,成交日,買賣別,成交股數\n2330,2025/01/01,現股買進,100\n", encoding="utf-8")
    detected = detect_file(path)
    assert detected.kind == FileKind.CSV
