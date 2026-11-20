"""CSV 解析。"""

from __future__ import annotations

import csv
from pathlib import Path

from backend.domain.exceptions import FileFormatError
from backend.ingest.html_parser import ParsedTable
from backend.ingest.mapping import MappingProfile, normalize_header


def parse_csv(path: Path, profile: MappingProfile, encoding: str = "utf-8-sig") -> ParsedTable:
    try:
        with path.open("r", encoding=encoding, newline="") as fh:
            sample = fh.read(4096)
            fh.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
            except csv.Error:
                dialect = csv.excel
            reader = csv.reader(fh, dialect)
            rows_raw = list(reader)
    except UnicodeDecodeError as exc:
        raise FileFormatError(f"CSV 解碼失敗（encoding={encoding}）") from exc

    if not rows_raw:
        raise FileFormatError("CSV 為空")

    headers = [normalize_header(h) for h in rows_raw[0]]
    rows: list[tuple[int, list[str]]] = []
    for i, row in enumerate(rows_raw[1:], start=2):
        if not any(str(c).strip() for c in row):
            continue
        values = [str(c) for c in row]
        if len(values) < len(headers):
            values += [""] * (len(headers) - len(values))
        elif len(values) > len(headers):
            values = values[: len(headers)]
        rows.append((i, values))
    return ParsedTable(headers=headers, rows=rows, sheet_name="csv")
