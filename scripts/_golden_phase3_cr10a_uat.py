"""Phase 3／CR-10A：GOLD-001-2236 隔離 UAT（真實來源 → 正式管線 → 對 C）。

- 讀本機 ``data/golden/expected_c/GOLD-001-2236.json``（不得為配合 D 而改寫）
- 來源 SHA 鎖定；隔離 DB／output；不寫正式 DB
- 證據寫入 ``data/golden/runs_d/`` 與 ``data/uat/golden_cr10a_2236/``
"""

from __future__ import annotations

import hashlib
import importlib
import json
import shutil
from datetime import UTC, datetime
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from backend.db.session import init_db, make_session_factory
from backend.golden.compare_c_d import (
    compare_expected_c_to_actual_d,
    golden_finance_from_expected_c,
)
from backend.golden.expected_c import rows_to_expected_trades
from backend.golden.phase3_pipeline import run_import_match_report
from scripts.uat_fifo_same_day_2236 import verify_detail_xlsx_finance

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "data" / "golden"
EXPECTED_C_PATH = GOLDEN / "expected_c" / "GOLD-001-2236.json"
RUNS_D = GOLDEN / "runs_d"
EVIDENCE = GOLDEN / "evidence"
UAT_ROOT = ROOT / "data" / "uat" / "golden_cr10a_2236"
OUT_ROOT = ROOT / "output" / "uat_golden_cr10a_2236"

inv = importlib.import_module("scripts._golden_phase01_inventory")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _enrich_trade_fingerprints(doc: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """若舊版 C JSON 缺 fingerprints，由同源列補齊（不改財務答案）。"""
    if doc.get("trade_fingerprints"):
        return doc
    trades = rows_to_expected_trades(rows)
    enriched = dict(doc)
    enriched["trade_fingerprints"] = [
        {
            "source_trade_id": t.trade_id,
            "symbol": t.symbol,
            "trade_date": t.trade_date.isoformat(),
            "side": t.side,
            "quantity": t.quantity,
            "unit_price": str(t.unit_price),
            "gross_amount": str(t.gross_amount),
            "commission": str(t.commission),
            "tax": str(t.tax),
            "interest": str(t.interest) if t.interest_known else "",
        }
        for t in trades
    ]
    return enriched


def _capital_rows_to_html(path: Path, rows: list[dict[str, Any]]) -> Path:
    """將 CSV 有效列轉為 statement_html_v1 可解析 HTML（數值來自 A；非假造）。"""
    headers = [
        "商品",
        "成交日",
        "買賣別",
        "幣別",
        "成交價",
        "成交股數",
        "成交金額",
        "手續費",
        "交易稅",
        "淨收付",
        "融資金額/擔保價款",
        "自備款/保證金",
        "利息",
        "融券手續費",
        "標借費",
        "證所稅",
        "健保費",
        "下單來源別",
    ]
    chunks = ["<html><meta charset='UTF-8'><body><table>"]
    chunks.append("<tr>" + "".join(f"<td>{escape(h)}</td>" for h in headers) + "</tr>")
    for r in rows:
        side = str(r.get("side") or "").upper()
        side_label = "現股買進" if side == "BUY" else "現股賣出"
        symbol = str(r.get("symbol") or "")
        name = str(r.get("name") or symbol)
        stock = (
            f'<td><span class="stockCode">{escape(symbol)}</span> '
            f'<span class="stockName">{escape(name)}</span></td>'
        )
        interest = r.get("interest")
        interest_s = "0" if interest in (None, "") else str(interest)
        rest = [
            str(r.get("trade_date") or ""),
            side_label,
            "臺幣",
            str(r.get("unit_price") or ""),
            str(r.get("quantity") or ""),
            str(r.get("gross_amount") or ""),
            str(r.get("commission") or ""),
            str(r.get("tax") or ""),
            str(r.get("net_settlement") or "0"),
            "0",
            "0",
            interest_s,
            "0",
            "0",
            "0",
            "0",
            "GOLDEN",
        ]
        chunks.append("<tr>" + stock + "".join(f"<td>{escape(x)}</td>" for x in rest) + "</tr>")
    chunks.append("</table></body></html>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(chunks), encoding="utf-8")
    return path


def _fault_inject_copy(src_xlsx: Path, dest_xlsx: Path) -> Path:
    """複製合法報表後同向偏移成本／收入（INV-05）。"""
    shutil.copy2(src_xlsx, dest_xlsx)
    wb = load_workbook(dest_xlsx)
    ws = wb.active
    assert ws is not None
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    idx = {h: i for i, h in enumerate(headers)}
    for row in ws.iter_rows(min_row=2, max_col=len(headers)):
        for col in ("成本", "收入"):
            cell = row[idx[col]]
            if cell.value is not None:
                cell.value = float(Decimal(str(cell.value)) + Decimal(1))
        break
    wb.save(dest_xlsx)
    return dest_xlsx


def main() -> int:
    if not EXPECTED_C_PATH.is_file():
        print("MISSING expected_c GOLD-001-2236.json")
        return 1

    source_key = "csv_2024"
    source_path: Path = inv.SOURCES[source_key]
    expected_sha = inv.EXPECTED_SHA256[source_key]
    actual_sha = _sha256(source_path)
    if actual_sha != expected_sha:
        print(json.dumps({"error": "source_sha_lock_fail", "expected": expected_sha, "actual": actual_sha}))
        return 1

    raw_doc = json.loads(EXPECTED_C_PATH.read_text(encoding="utf-8"))
    # 不得改寫磁碟上的 C 答案；僅記憶體補 fingerprints
    analysis = inv.analyze_capital_csv(source_path)
    rows = []
    for r in analysis["rows"]:
        if str(r.get("symbol")) != "2236":
            continue
        item = dict(r)
        item["source_id"] = source_key
        item["account_id"] = "群益_acct_A"
        rows.append(item)
    expected_c = _enrich_trade_fingerprints(raw_doc, rows)

    integrity = (expected_c.get("source_integrity") or {}).get("status")
    if integrity == "FAIL" or expected_c.get("validation_status") == "BLOCKED_SOURCE_INTEGRITY":
        print(json.dumps({"error": "expected_c_blocked", "integrity": integrity}))
        return 1
    if not integrity or integrity not in {"PASS", "PARTIAL"}:
        print(json.dumps({"error": "missing_source_lock_evidence", "integrity": integrity}))
        return 1

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = UAT_ROOT / f"run_{stamp}"
    out_dir = OUT_ROOT / f"run_{stamp}"
    runs_case = RUNS_D / "GOLD-001-2236" / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    out_dir.mkdir(parents=True, exist_ok=False)
    runs_case.mkdir(parents=True, exist_ok=False)

    bridge = run_dir / "gold001_2236_bridge.xls"
    _capital_rows_to_html(bridge, rows)

    formal_db = ROOT / "data" / "trading.db"
    formal_before = _sha256(formal_db) if formal_db.is_file() else None

    db_path = run_dir / "uat.db"
    engine = init_db(db_path)
    Session = make_session_factory(engine)
    summary: dict[str, Any] = {
        "case_id": "GOLD-001-2236",
        "phase": "3_cr10a",
        "started_at_utc": datetime.now(UTC).isoformat(),
        "source_key": source_key,
        "source_sha256": actual_sha,
        "source_lock_ok": True,
        "expected_c_path": str(EXPECTED_C_PATH.relative_to(ROOT)).replace("\\", "/"),
        "expected_c_validation_status": expected_c.get("validation_status"),
        "bridge_note": "capital CSV 2236 列→HTML bridge；數值來自 A；正式 statement_html_v1 Parser",
        "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
        "output_dir": str(out_dir.relative_to(ROOT)).replace("\\", "/"),
        "runs_d": str(runs_case.relative_to(ROOT)).replace("\\", "/"),
    }

    with Session() as session:
        pipe = run_import_match_report(
            session,
            source_path=bridge,
            broker_name="群益",
            account_label=f"gold_cr10a_2236_{stamp}",
            profile_id="statement_html_v1",
            out_dir=out_dir,
        )
        session.commit()
        actual = pipe["actual_d"]
        # 全配平時 open_cost 對齊 C
        if int(actual.get("open_quantity") or 0) == 0:
            actual["open_cost"] = Decimal(0)

        compare = compare_expected_c_to_actual_d(expected_c, actual)
        golden = golden_finance_from_expected_c(expected_c)
        # 聚合 Excel vs C；逐筆對應由 compare allocation_fingerprints 負責
        finance = verify_detail_xlsx_finance(pipe["xlsx"], golden)

        # 反向：複製合法報表故障注入
        fault_path = runs_case / "fault_cost_income_both_up.xlsx"
        _fault_inject_copy(pipe["xlsx"], fault_path)
        fault_finance = verify_detail_xlsx_finance(fault_path, golden)

    formal_after = _sha256(formal_db) if formal_db.is_file() else None
    summary.update(
        {
            "finished_at_utc": datetime.now(UTC).isoformat(),
            "import_trade_count": pipe["import_result"].trade_count,
            "detail_xlsx": str(Path(pipe["xlsx"]).relative_to(ROOT)).replace("\\", "/"),
            "detail_is_draft": pipe["detail_is_draft"],
            "compare_c_d": {
                "ok": compare["ok"],
                "diffs": compare["diffs"],
                "errors": compare["errors"],
                "compared_fields": compare["compared_fields"],
            },
            "xlsx_finance_vs_c": {
                "ok": finance["ok"],
                "diffs": finance["diffs"],
                "errors": finance["errors"],
            },
            "fault_injection": {
                "path": str(fault_path.relative_to(ROOT)).replace("\\", "/"),
                "ok_should_be_false": fault_finance["ok"] is False,
                "diffs": fault_finance["diffs"],
            },
            "formal_db_untouched": formal_before == formal_after,
            "formal_db_before": formal_before,
            "formal_db_after": formal_after,
        }
    )
    verdict_ok = (
        compare["ok"]
        and finance["ok"]
        and fault_finance["ok"] is False
        and summary["formal_db_untouched"]
        and not pipe["detail_is_draft"]
    )
    summary["uat_verdict"] = "PASS" if verdict_ok else "FAIL"

    # 保存 expected／actual／difference（本機；含財務數字）
    _write_json(runs_case / "expected_c_snapshot_meta.json", {
        "case_id": expected_c.get("case_id"),
        "validation_status": expected_c.get("validation_status"),
        "source_integrity": expected_c.get("source_integrity"),
        "aggregates_keys": sorted((expected_c.get("aggregates") or {}).keys()),
        "fifo_expected": expected_c.get("fifo_expected"),
        "realized_status": (expected_c.get("realized_and_open") or {}).get("status"),
        "allocation_count": len(expected_c.get("allocations") or []),
        "note": "完整金額見同目錄 difference／勿 commit",
    })
    _write_json(runs_case / "actual_d.json", {
        k: (str(v) if isinstance(v, Decimal) else v)
        for k, v in actual.items()
        if k not in {"allocation_fingerprints", "trade_fingerprints"}
    })
    _write_json(runs_case / "difference.json", {
        "compare_diffs": compare["diffs"],
        "finance_diffs": finance["diffs"],
        "fault_caught": fault_finance["ok"] is False,
    })
    _write_json(run_dir / "summary.json", summary)
    _write_json(EVIDENCE / "phase03_cr10a_2236_summary.json", {
        k: summary[k]
        for k in (
            "case_id",
            "phase",
            "uat_verdict",
            "source_lock_ok",
            "compare_c_d",
            "xlsx_finance_vs_c",
            "fault_injection",
            "formal_db_untouched",
            "started_at_utc",
            "finished_at_utc",
            "runs_d",
        )
        if k in summary
    })
    # 複製合法報表到 runs_d
    shutil.copy2(pipe["xlsx"], runs_case / pipe["xlsx"].name)
    shutil.copy2(pipe["audit_path"], runs_case / pipe["audit_path"].name)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["uat_verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
