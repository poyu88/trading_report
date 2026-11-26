"""私有測資閘門：缺檔 skip／有檔載入；不得缺檔冒充 PASS。

SOURCE: SYNTHETIC_CONTRACT（以臨時合成 JSON 測載入器；非真實交易）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.private_fixtures import (
    PRIVATE_FIXTURE_UNAVAILABLE,
    assert_priv_equal,
    load_original_rows_2236,
    private_fixture_unavailable_reason,
    require_private_json,
)


def test_missing_private_fixture_skips_with_marker(tmp_path: Path) -> None:
    missing = tmp_path / "absent.json"
    reason = private_fixture_unavailable_reason(missing)
    assert PRIVATE_FIXTURE_UNAVAILABLE in reason
    with pytest.raises(pytest.skip.Exception) as exc:
        require_private_json(missing)
    assert PRIVATE_FIXTURE_UNAVAILABLE in str(exc.value)


def test_load_synthetic_private_shape(tmp_path: Path) -> None:
    """合成最小 shape 驗證載入契約（非 REAL_DERIVED 九筆）。"""
    path = tmp_path / "mini.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": "SYNTHETIC_UNIT",
                "rows": [
                    {
                        "symbol": "0000",
                        "name": "synthetic",
                        "date": "2099/01/01",
                        "side": "BUY",
                        "price": "1",
                        "qty": 1,
                        "gross": "1",
                        "commission": "0",
                        "tax": "0",
                        "net": "-1",
                    }
                ],
                "expected": {"raw_count": 1, "buy_qty": 1, "sell_qty": 0},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    rows, expected = load_original_rows_2236(path)
    assert len(rows) == 1
    assert_priv_equal(expected["raw_count"], 1, "raw_count")
    assert_priv_equal(rows[0]["side"], "BUY", "side")


def test_assert_priv_equal_hides_values_in_message() -> None:
    with pytest.raises(AssertionError) as exc:
        assert_priv_equal(1, 2, "demo_field")
    msg = str(exc.value)
    assert msg == "private_mismatch:demo_field"


def test_corrupt_json_fails_not_skip(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(AssertionError, match="private_fixture:json_invalid"):
        require_private_json(path)


def test_missing_rows_fails_not_skip(tmp_path: Path) -> None:
    path = tmp_path / "empty_rows.json"
    path.write_text(
        json.dumps({"schema_version": 1, "source": "SYNTHETIC_UNIT", "rows": [], "expected": {}}),
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="private_fixture:rows_missing"):
        load_original_rows_2236(path)


def test_official_path_rejects_non_real_derived(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """正式路徑檔存在但 source 不符 → FAIL（非 skip）。"""
    path = tmp_path / "original_rows_2236.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": "SYNTHETIC_UNIT",
                "rows": [
                    {
                        "symbol": "0000",
                        "name": "x",
                        "date": "2099/01/01",
                        "side": "BUY",
                        "price": "1",
                        "qty": 1,
                        "gross": "1",
                        "commission": "0",
                        "tax": "0",
                        "net": "-1",
                    }
                ],
                "expected": {"raw_count": 1, "buy_qty": 1, "sell_qty": 0},
            }
        ),
        encoding="utf-8",
    )
    import tests.private_fixtures as pf

    monkeypatch.setattr(pf, "ORIGINAL_ROWS_2236_PATH", path)
    with pytest.raises(AssertionError, match="private_fixture:source_invalid"):
        pf.load_original_rows_2236()
