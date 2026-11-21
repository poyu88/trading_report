"""載入與套用 mapping profile。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.config import PROFILES_DIR
from backend.domain.exceptions import ProfileError


def normalize_header(text: str) -> str:
    """正規化表頭：去 HTML 換行、空白、全形空白。"""
    cleaned = re.sub(r"<br\s*/?>", "", text, flags=re.IGNORECASE)
    cleaned = cleaned.replace("\u3000", " ").replace("\xa0", " ")
    cleaned = re.sub(r"\s+", "", cleaned)
    return cleaned.strip()


@dataclass(frozen=True)
class MappingProfile:
    profile_id: str
    version: int
    source_format: str
    table_index: int
    required_headers: list[str]
    column_map: dict[str, str]
    exclude_row_prefixes: list[str]
    side_map: dict[str, str]
    currency_map: dict[str, str]
    date_formats: list[str]
    gross_tolerance: str
    unsupported_sides: dict[str, str]
    trade_type_map: dict[str, str]
    default_currency: str | None
    raw: dict[str, Any]

    @property
    def normalized_column_map(self) -> dict[str, str]:
        return {normalize_header(k): v for k, v in self.column_map.items()}

    @property
    def normalized_required(self) -> list[str]:
        return [normalize_header(h) for h in self.required_headers]


def load_profile(profile_id: str, profiles_dir: Path | None = None) -> MappingProfile:
    directory = profiles_dir or PROFILES_DIR
    path = directory / f"{profile_id}.json"
    if not path.is_file():
        raise ProfileError(f"找不到 profile：{path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    try:
        return MappingProfile(
            profile_id=data["profile_id"],
            version=int(data["version"]),
            source_format=data["source_format"],
            table_index=int(data.get("table_index", 0)),
            required_headers=list(data["required_headers"]),
            column_map=dict(data["column_map"]),
            exclude_row_prefixes=list(data.get("exclude_row_prefixes", [])),
            side_map=dict(data.get("side_map", {})),
            currency_map=dict(data.get("currency_map", {})),
            date_formats=list(data.get("date_formats", ["%Y/%m/%d"])),
            gross_tolerance=str(data.get("gross_tolerance", "1")),
            unsupported_sides=dict(data.get("unsupported_sides", {})),
            trade_type_map=dict(data.get("trade_type_map", {})),
            default_currency=data.get("default_currency"),
            raw=data,
        )
    except KeyError as exc:
        raise ProfileError(f"profile 缺少必要欄位：{exc}") from exc


def map_row(headers: list[str], values: list[str], profile: MappingProfile) -> dict[str, str]:
    """依 profile 將一列原始值映射為 canonical 欄位。"""
    norm_headers = [normalize_header(h) for h in headers]
    col_map = profile.normalized_column_map
    missing = [h for h in profile.normalized_required if h not in norm_headers]
    if missing:
        raise ProfileError(f"來源缺少必要表頭：{missing}")

    mapped: dict[str, str] = {}
    for header, value in zip(norm_headers, values, strict=False):
        key = col_map.get(header)
        if key:
            mapped[key] = value
    return mapped
