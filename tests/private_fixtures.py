"""本機私有測資載入（gitignored）；CI 缺檔時標記 PRIVATE_FIXTURE_UNAVAILABLE。

不得將真實交易明細提交公開 Git。失敗訊息只含欄位標籤，不含財務數值。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_FIXTURES_DIR = REPO_ROOT / "data" / "golden" / "private_fixtures"
ORIGINAL_ROWS_2236_PATH = PRIVATE_FIXTURES_DIR / "original_rows_2236.json"

PRIVATE_FIXTURE_UNAVAILABLE = "PRIVATE_FIXTURE_UNAVAILABLE"


def private_fixture_unavailable_reason(path: Path) -> str:
    """回傳標準 skip reason（可被 CI／本機辨識）。"""
    rel = path.as_posix()
    try:
        rel = path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        pass
    return f"{PRIVATE_FIXTURE_UNAVAILABLE}: missing {rel}"


def require_private_json(path: Path) -> dict[str, Any]:
    """載入私有 JSON；缺檔則 pytest.skip（不得視為 PASS）。

    檔案存在但 JSON／結構不合法時必須 FAIL，不得靜默 skip。
    """
    if not path.is_file():
        pytest.skip(private_fixture_unavailable_reason(path))
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AssertionError("private_fixture:json_invalid") from exc
    if not isinstance(raw, dict):
        raise TypeError("private_fixture:root_not_object")
    return raw


_REQUIRED_ROW_KEYS = (
    "symbol",
    "name",
    "date",
    "side",
    "price",
    "qty",
    "gross",
    "commission",
    "tax",
    "net",
)


def load_original_rows_2236(
    path: Path | None = None,
) -> tuple[list[dict[str, str | int]], dict[str, Any]]:
    """載入 REAL_DERIVED 九筆列與 expected 元資料。

    Returns:
        (rows, expected)

    Raises:
        AssertionError: 檔案存在但格式／必要欄位不符（FAIL，非 skip）。
    """
    target = path or ORIGINAL_ROWS_2236_PATH
    official = path is None
    doc = require_private_json(target)
    rows = doc.get("rows")
    expected = doc.get("expected")
    if not isinstance(rows, list) or not rows:
        raise AssertionError("private_fixture:rows_missing")
    if not isinstance(expected, dict) or not expected:
        raise AssertionError("private_fixture:expected_missing")
    if official:
        # 正式 fixture：強制 REAL_DERIVED 與九列契約；不符則 FAIL（非 skip）
        if doc.get("source") != "REAL_DERIVED":
            raise AssertionError("private_fixture:source_invalid")
        if len(rows) != 9:
            raise AssertionError("private_fixture:row_count_invalid")
        for row in rows:
            if not isinstance(row, dict):
                raise TypeError("private_fixture:row_not_object")
            for key in _REQUIRED_ROW_KEYS:
                if key not in row:
                    raise AssertionError("private_fixture:row_key_missing")
        for key in ("raw_count", "buy_qty", "sell_qty", "triple_day_slash", "odd_day_slash"):
            if key not in expected:
                raise AssertionError("private_fixture:expected_key_missing")
    return rows, expected  # type: ignore[return-value]


def assert_priv_equal(actual: object, expected: object, label: str) -> None:
    """比對私有值；失敗只報告標籤，避免 pytest 差分洩漏明細。"""
    if actual != expected:
        raise AssertionError(f"private_mismatch:{label}")


def assert_priv_true(cond: bool, label: str) -> None:
    """條件斷言；失敗不帶入財務運算元。"""
    if not cond:
        raise AssertionError(f"private_mismatch:{label}")
