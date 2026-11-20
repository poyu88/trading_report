"""輸出 audit.json 與 exceptions.csv。"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from backend.domain.models import DetailRow
from backend.services.reconciliation import AuditSummary


def write_audit_files(
    output_xlsx: Path,
    audit: AuditSummary,
    rows: list[DetailRow],
    extra: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    stem = output_xlsx.with_suffix("")
    audit_path = Path(f"{stem}_audit.json")
    exc_path = Path(f"{stem}_exceptions.csv")

    index = [
        {
            "row": i + 2,
            "symbol": r.symbol,
            "buy_trade_id": r.buy_trade_id,
            "sell_trade_id": r.sell_trade_id,
            "opening_lot_id": r.opening_lot_id,
            "allocation_id": r.allocation_id,
            "buy_qty": r.buy_qty,
            "sell_qty": r.sell_qty,
        }
        for i, r in enumerate(rows)
    ]

    payload = {
        "account_id": audit.account_id,
        "allocation_run_id": audit.run_id,
        "trade_count": audit.trade_count,
        "buy_count": audit.buy_count,
        "sell_count": audit.sell_count,
        "allocation_count": audit.allocation_count,
        "issue_count": audit.issue_count,
        "blocking_issue_count": audit.blocking_issue_count,
        "conservation_ok": audit.conservation_ok,
        "commission_total": audit.commission_total,
        "tax_total": audit.tax_total,
        "detail_row_count": len(rows),
        "output_file": str(output_xlsx),
        "issues": audit.issues,
        "detail_index": index,
        **(extra or {}),
    }
    audit_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with exc_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["issue_id", "code", "severity", "trade_id", "detail_json"],
        )
        writer.writeheader()
        for issue in audit.issues:
            writer.writerow(
                {
                    "issue_id": issue["id"],
                    "code": issue["code"],
                    "severity": issue["severity"],
                    "trade_id": issue.get("trade_id") or "",
                    "detail_json": json.dumps(issue.get("detail", {}), ensure_ascii=False),
                }
            )

    return audit_path, exc_path
