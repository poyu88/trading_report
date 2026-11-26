"""Phase 3：GOLD-004 全年度實際 D 回歸（可驗證範圍；不強制完整 PASS）。

SOURCE: REAL_SOURCE（本機 gitignored CSV／C）→ REAL_DERIVED（HTML bridge）
四年度原始 CSV → HTML bridge → 正式 Import／FIFO／Report → 對獨立 C。
HTML bridge 僅驗轉換後匯入與後續流程；不得宣稱原始 CSV Parser 已獨立驗收（PENDING_DATA）。
"""

from __future__ import annotations

import importlib
import json
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any

from backend.db.session import init_db, make_session_factory
from backend.golden.compare_c_d import (
    compare_allocation_lines_to_trace_rows,
    compare_expected_c_to_actual_d,
    golden_finance_from_expected_c,
)
from backend.golden.expected_c import rows_to_expected_trades
from backend.golden.phase3_pipeline import (
    decide_gold004_verdict,
    read_fifo_trace_rows,
    run_import_match_report,
)
from scripts.uat_fifo_same_day_2236 import verify_detail_xlsx_finance

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "data" / "golden"
EXPECTED_C_PATH = GOLDEN / "expected_c" / "GOLD-004.json"
RUNS_D = GOLDEN / "runs_d"
EVIDENCE = GOLDEN / "evidence"
UAT_ROOT = ROOT / "data" / "uat" / "golden_cr10a_004"
OUT_ROOT = ROOT / "output" / "uat_golden_cr10a_004"

inv = importlib.import_module("scripts._golden_phase01_inventory")
YEAR_KEYS = ("csv_2023", "csv_2024", "csv_2025", "csv_2026")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _rows_to_html(path: Path, rows: list[dict[str, Any]]) -> Path:
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
            "GOLD004",
        ]
        chunks.append("<tr>" + stock + "".join(f"<td>{escape(x)}</td>" for x in rest) + "</tr>")
    chunks.append("</table></body></html>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(chunks), encoding="utf-8")
    return path


def main() -> int:
    if not EXPECTED_C_PATH.is_file():
        print("MISSING GOLD-004 expected_c")
        return 1

    # 來源鎖定：四年度
    lock_ok = True
    lock_detail = {}
    for key in YEAR_KEYS:
        path = inv.SOURCES[key]
        sha = inv.sha256_file(path)
        exp = inv.EXPECTED_SHA256[key]
        ok = sha == exp
        lock_detail[key] = {"ok": ok, "sha256": sha}
        lock_ok = lock_ok and ok
    if not lock_ok:
        print(json.dumps({"error": "source_sha_lock_fail", "detail": lock_detail}))
        return 1

    raw_doc = json.loads(EXPECTED_C_PATH.read_text(encoding="utf-8"))
    all_rows: list[dict[str, Any]] = []
    for key in YEAR_KEYS:
        analysis = inv.analyze_capital_csv(inv.SOURCES[key])
        for r in analysis["rows"]:
            item = dict(r)
            item["source_id"] = key
            item["account_id"] = "群益_acct_A"
            all_rows.append(item)

    if not raw_doc.get("trade_fingerprints"):
        trades = rows_to_expected_trades(all_rows)
        raw_doc = dict(raw_doc)
        raw_doc["trade_fingerprints"] = [
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

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = UAT_ROOT / f"run_{stamp}"
    out_dir = OUT_ROOT / f"run_{stamp}"
    runs_case = RUNS_D / "GOLD-004" / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    out_dir.mkdir(parents=True, exist_ok=False)
    runs_case.mkdir(parents=True, exist_ok=False)

    fp_before = inv.fingerprint_bundle("phase3_gold004_before")
    bridge = run_dir / "gold004_all_years_bridge.xls"
    _rows_to_html(bridge, all_rows)

    engine = init_db(run_dir / "uat.db")
    Session = make_session_factory(engine)
    pending: list[str] = []
    with Session() as session:
        pipe = run_import_match_report(
            session,
            source_path=bridge,
            broker_name="群益",
            account_label=f"gold004_{stamp}",
            profile_id="statement_html_v1",
            out_dir=out_dir,
        )
        session.commit()
        actual = pipe["actual_d"]
        compare = compare_expected_c_to_actual_d(raw_doc, actual)
        golden = golden_finance_from_expected_c(raw_doc)
        golden_agg = {
            k: v
            for k, v in golden.items()
            if k not in {"per_row_costs", "per_row_incomes", "per_row_lines"}
        }
        finance = verify_detail_xlsx_finance(pipe["xlsx"], golden_agg)
        audit = json.loads(pipe["audit_path"].read_text(encoding="utf-8"))
        trace_path = Path(str(audit["fifo_trace_file"]))
        per_line = compare_allocation_lines_to_trace_rows(
            raw_doc,
            read_fifo_trace_rows(trace_path),
            trade_id_to_fp=actual.get("trade_id_to_fp") or {},
        )
        if actual.get("open_cost_status") in {"NOT_VERIFIED", "PENDING_DATA"}:
            pending.append("open_cost_not_verified")
        if pipe["detail_is_draft"]:
            pending.append("detail_is_draft_partial")

    fp_after = inv.fingerprint_bundle("phase3_gold004_after")
    drift = inv.compare_fingerprint_bundles(fp_before, fp_after)

    formal_ok = drift.get("status") == "PASS"
    decided = decide_gold004_verdict(
        compare_ok=bool(compare["ok"]),
        finance_ok=bool(finance["ok"]),
        per_line_ok=bool(per_line["ok"]),
        artifacts_ok=bool(pipe["artifacts"]["ok"]),
        formal_db_untouched=bool(formal_ok),
        pending_data=pending,
    )
    verdict = str(decided["verdict"])
    # Excel 明細以聚合為主；逐筆財務靠 Trace↔C。以下 Excel 欄未做可靠逐欄對應。
    excel_unverified = [
        "成交單價（買／賣）逐欄",
        "備註／annotation 欄",
        "非聚合明細列順序",
        "原始 CSV Parser（本腳本僅 HTML bridge）",
    ]

    summary = {
        "case_id": "GOLD-004",
        "phase": "3_gold004_wrap",
        "uat_verdict": verdict,
        "exit_code": int(decided["exit_code"]),
        "necessary_ok": decided["necessary_ok"],
        "source_lock_ok": lock_ok,
        "bridge_note": (
            "HTML bridge only；原始 CSV Parser 未宣稱獨立驗收；"
            "不得將 bridge 宣稱為 CSV Parser 完整驗收"
        ),
        "import_trade_count": pipe["import_result"].trade_count,
        "expected_trade_count": raw_doc.get("trade_count"),
        "compare_c_d_ok": compare["ok"],
        "compare_diffs": compare["diffs"],
        "finance_ok": finance["ok"],
        "per_line_ok": per_line["ok"],
        "per_line_expected_count": per_line.get("expected_line_count"),
        "per_line_actual_count": per_line.get("actual_matched_count"),
        "artifacts_ok": pipe["artifacts"]["ok"],
        "formal_db_untouched": formal_ok,
        "pending_data": decided["pending_data"],
        "excel_verification_scope": {
            "mode": "aggregate_primary",
            "per_line_via": "allocation_lines_to_fifo_trace",
            "unverified_fields": excel_unverified,
        },
        "known_limitations": list(raw_doc.get("known_limitations") or [])[:8],
        "started_at_utc": datetime.now(UTC).isoformat(),
        "runs_d": str(runs_case.relative_to(ROOT)).replace("\\", "/"),
    }
    _write_json(run_dir / "summary.json", summary)
    _write_json(runs_case / "difference.json", {
        "compare_diffs": compare["diffs"],
        "finance_diffs": finance["diffs"],
        "per_line_diffs": per_line["diffs"],
        "failed_necessary": [
            name
            for name, ok in (
                ("compare_c_d", compare["ok"]),
                ("finance", finance["ok"]),
                ("per_line", per_line["ok"]),
                ("artifacts", pipe["artifacts"]["ok"]),
                ("formal_db", formal_ok),
            )
            if not ok
        ],
    })
    _write_json(EVIDENCE / "phase03_gold004_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return int(decided["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
