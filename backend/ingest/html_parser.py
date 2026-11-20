"""解析 HTML 偽 XLS 表格。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup

from backend.domain.exceptions import FileFormatError
from backend.ingest.mapping import MappingProfile, normalize_header


@dataclass(frozen=True)
class ParsedTable:
    headers: list[str]
    rows: list[tuple[int, list[str]]]  # (row_index, cell values)
    sheet_name: str = "table0"


def _cell_text(cell) -> str:  # type: ignore[no-untyped-def]
    stock_code = cell.select_one(".stockCode")
    stock_name = cell.select_one(".stockName")
    if stock_code or stock_name:
        code = stock_code.get_text(strip=True) if stock_code else ""
        name = stock_name.get_text(strip=True) if stock_name else ""
        return f"{code} {name}".strip()
    return cell.get_text(" ", strip=True)


def parse_html_table(path: Path, profile: MappingProfile, encoding: str = "utf-8") -> ParsedTable:
    text = path.read_text(encoding=encoding)
    soup = BeautifulSoup(text, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        raise FileFormatError("HTML 中找不到 table")
    if profile.table_index >= len(tables):
        raise FileFormatError(f"table_index={profile.table_index} 超出範圍")

    table = tables[profile.table_index]
    trs = table.find_all("tr")
    if not trs:
        raise FileFormatError("表格沒有列")

    header_cells = trs[0].find_all(["td", "th"])
    headers = [normalize_header(_cell_text(c)) for c in header_cells]
    if not headers:
        raise FileFormatError("表格沒有表頭")

    rows: list[tuple[int, list[str]]] = []
    for idx, tr in enumerate(trs[1:], start=2):  # 1-based with header as row 1
        cells = tr.find_all(["td", "th"])
        values = [_cell_text(c) for c in cells]
        if not any(v.strip() for v in values):
            continue
        # 對齊欄位數
        if len(values) < len(headers):
            values = values + [""] * (len(headers) - len(values))
        elif len(values) > len(headers):
            values = values[: len(headers)]
        rows.append((idx, values))

    return ParsedTable(headers=headers, rows=rows, sheet_name=f"table{profile.table_index}")
