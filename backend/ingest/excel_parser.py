"""真正的 XLS / XLSX 解析（python-calamine）。"""

from __future__ import annotations

from pathlib import Path

from python_calamine import CalamineWorkbook

from backend.domain.exceptions import FileFormatError
from backend.ingest.html_parser import ParsedTable
from backend.ingest.mapping import MappingProfile, normalize_header


def parse_excel(path: Path, profile: MappingProfile, sheet_name: str | None = None) -> ParsedTable:
    try:
        workbook = CalamineWorkbook.from_path(str(path))
    except Exception as exc:
        raise FileFormatError(f"無法讀取 Excel：{exc}") from exc

    names = workbook.sheet_names
    if not names:
        raise FileFormatError("Excel 沒有工作表")
    target = sheet_name or names[0]
    if target not in names:
        raise FileFormatError(f"找不到工作表：{target}")

    sheet = workbook.get_sheet_by_name(target)
    data = sheet.to_python(skip_empty_area=False)
    if not data:
        raise FileFormatError("工作表為空")

    headers = [normalize_header("" if c is None else str(c)) for c in data[0]]
    rows: list[tuple[int, list[str]]] = []
    for i, row in enumerate(data[1:], start=2):
        values = ["" if c is None else str(c) for c in row]
        if not any(v.strip() for v in values):
            continue
        if len(values) < len(headers):
            values += [""] * (len(headers) - len(values))
        elif len(values) > len(headers):
            values = values[: len(headers)]
        rows.append((i, values))
    return ParsedTable(headers=headers, rows=rows, sheet_name=target)
