"""Phase 3：GOLD-002／003／004 依現有 C 答案範圍驗收（不足維持 PENDING_DATA）。

不補造期初；不把未知欄位預設為 0；不寫正式 DB。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_C = ROOT / "data" / "golden" / "expected_c"
EVIDENCE = ROOT / "data" / "golden" / "evidence"
RUNS_D = ROOT / "data" / "golden" / "runs_d"


def _load(case_id: str) -> dict[str, Any] | None:
    path = EXPECTED_C / f"{case_id}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _assess(case_id: str, doc: dict[str, Any]) -> dict[str, Any]:
    integrity = (doc.get("source_integrity") or {}).get("status")
    status = doc.get("validation_status")
    fields_not = list(doc.get("fields_not_computable") or [])
    agg = doc.get("aggregates") or {}
    fifo = doc.get("fifo_expected") or {}
    realized = doc.get("realized_and_open") or {}

    confirmed: list[str] = []
    pending: list[str] = []

    if integrity == "PASS":
        confirmed.append("source_integrity_pass")
    elif integrity == "PARTIAL":
        confirmed.append("source_integrity_partial_known")
        pending.append("full_source_integrity")
    else:
        pending.append("source_integrity")

    if agg.get("valid_trade_count") is not None:
        confirmed.append("aggregates_valid_trade_count")
    if agg.get("interest_known") is False:
        pending.append("interest_unknown_rows")
    if "unknown_currency_rows" in fields_not:
        pending.append("unknown_currency")
    if "DAY_TRADE_OR_UNKNOWN_TYPE_NOT_IN_CASH_FIFO" in fields_not:
        pending.append("day_trade_cash_fifo")
    if any("opening" in f.lower() for f in fields_not):
        pending.append("opening_lots")

    if status == "INDEPENDENTLY_COMPUTED":
        confirmed.extend(
            [
                "fifo_expected",
                "allocation_lines",
                "realized_and_open",
            ]
        )
        acceptance = "FULL_C_READY"
    elif status == "INDEPENDENTLY_COMPUTED_PARTIAL":
        if fifo:
            confirmed.append("fifo_partial_scope")
        if realized.get("status") == "COMPUTED":
            confirmed.append("realized_partial_computed")
        else:
            pending.append("realized_incomplete")
        acceptance = "PARTIAL_CONFIRMED_FIELDS_ONLY"
    elif status == "BLOCKED_SOURCE_INTEGRITY":
        acceptance = "BLOCKED"
        pending.append("blocked_source")
    else:
        acceptance = "PENDING_DATA"

    return {
        "case_id": case_id,
        "validation_status": status,
        "source_integrity": integrity,
        "acceptance": acceptance,
        "confirmed_fields": confirmed,
        "pending_data": pending,
        "fields_not_computable": fields_not,
        "trade_count": doc.get("trade_count"),
        "allocation_count": len(doc.get("allocations") or []),
        "note": "PARTIAL 僅驗已確認欄；缺期初／未知幣別／DAY_TRADE 維持 PENDING_DATA",
    }


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    results = []
    exit_code = 0
    for case_id in ("GOLD-002", "GOLD-003", "GOLD-004"):
        doc = _load(case_id)
        if doc is None:
            results.append(
                {
                    "case_id": case_id,
                    "acceptance": "PENDING_DATA",
                    "pending_data": ["missing_expected_c_json"],
                }
            )
            continue
        if (doc.get("source_integrity") or {}).get("status") == "FAIL":
            exit_code = 1
        assessed = _assess(case_id, doc)
        results.append(assessed)
        out = RUNS_D / case_id / stamp
        out.mkdir(parents=True, exist_ok=True)
        (out / "partial_assessment.json").write_text(
            json.dumps(assessed, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    summary = {
        "phase": "3_partial_cases",
        "built_at_utc": datetime.now(UTC).isoformat(),
        "cases": results,
        "exit_code": exit_code,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "phase03_partial_cases_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
