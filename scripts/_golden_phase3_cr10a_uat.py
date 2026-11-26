"""Phase 3／CR-10A：GOLD-001-2236 隔離 UAT（真實來源 → 正式管線 → 對 C）。

SOURCE: REAL_SOURCE（本機 gitignored）→ REAL_DERIVED（HTML bridge）
- 讀本機 ``data/golden/expected_c/GOLD-001-2236.json``（不得為配合 D 而改寫）
- 來源 SHA 鎖定；隔離 DB／output；不寫正式 DB
- 證據寫入 ``data/golden/runs_d/`` 與 ``data/uat/golden_cr10a_2236/``（不上傳 Git）
- 缺檔時不得宣稱 PASS。
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
    compare_allocation_lines_to_trace_rows,
    compare_expected_c_to_actual_d,
    golden_finance_from_expected_c,
)
from backend.golden.expected_c import rows_to_expected_trades
from backend.golden.phase3_pipeline import (
    read_fifo_trace_rows,
    run_import_match_report,
)
from scripts.uat_fifo_same_day_2236 import (
    build_uat_checks,
    resolve_required_outputs,
    uat_exit_code,
    verify_detail_xlsx_finance,
)

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


def _fault_inject_per_row_offset(src_xlsx: Path, dest_xlsx: Path) -> Path:
    """複製合法報表：列0成本／收入+1、列1−1（總額不變之互抵）。"""
    shutil.copy2(src_xlsx, dest_xlsx)
    wb = load_workbook(dest_xlsx)
    ws = wb.active
    assert ws is not None
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    idx = {h: i + 1 for i, h in enumerate(headers)}
    data_rows = [
        r
        for r in range(2, (ws.max_row or 1) + 1)
        if any(ws.cell(r, c).value is not None for c in range(1, len(headers) + 1))
    ]
    if len(data_rows) < 2:
        raise RuntimeError("need_at_least_two_detail_rows_for_per_row_offset")
    r0, r1 = data_rows[0], data_rows[1]
    for col in ("成本", "收入"):
        c0 = ws.cell(r0, idx[col])
        c1 = ws.cell(r1, idx[col])
        c0.value = float(Decimal(str(c0.value or 0)) + Decimal(1))
        c1.value = float(Decimal(str(c1.value or 0)) - Decimal(1))
    wb.save(dest_xlsx)
    return dest_xlsx


def _fault_inject_trace_line(src_trace: Path, dest_trace: Path) -> Path:
    """複製 Trace：第一筆 MATCHED 成本／收入同向 +1。"""
    shutil.copy2(src_trace, dest_trace)
    wb = load_workbook(dest_trace)
    ws = wb.active
    assert ws is not None
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    idx = {h: i for i, h in enumerate(headers)}
    for row in ws.iter_rows(min_row=2, max_col=len(headers)):
        if row[idx["列語意"]].value != "MATCHED":
            continue
        for col in ("成本", "收入"):
            cell = row[idx[col]]
            if cell.value is not None:
                cell.value = float(Decimal(str(cell.value)) + Decimal(1))
        break
    wb.save(dest_trace)
    return dest_trace


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

    fp_before = inv.fingerprint_bundle("phase3_cr10a_before")
    _write_json(run_dir / "formal_fp_before.json", fp_before)

    db_path = run_dir / "uat.db"
    engine = init_db(db_path)
    Session = make_session_factory(engine)
    summary: dict[str, Any] = {
        "case_id": "GOLD-001-2236",
        "phase": "3_cr10a_r2",
        "started_at_utc": datetime.now(UTC).isoformat(),
        "source_key": source_key,
        "source_sha256": actual_sha,
        "source_lock_ok": True,
        "expected_c_path": str(EXPECTED_C_PATH.relative_to(ROOT)).replace("\\", "/"),
        "expected_c_validation_status": expected_c.get("validation_status"),
        "bridge_note": (
            "HTML bridge＝轉換後 HTML 匯入及後續 FIFO／Report 驗收；"
            "不得宣稱原始 CSV Parser 已獨立驗收"
        ),
        "isolation": {
            "db_under_data_uat": True,
            "out_under_output_uat": True,
            "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
            "output_dir": str(out_dir.relative_to(ROOT)).replace("\\", "/"),
        },
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
        # 不得用 expected_c 填補 actual open_cost
        compare = compare_expected_c_to_actual_d(expected_c, actual)
        golden = golden_finance_from_expected_c(expected_c)
        # 聚合驗收：不含順序相依 per_row（逐筆改由 Trace 指紋對應）
        golden_agg = {
            k: v
            for k, v in golden.items()
            if k not in {"per_row_costs", "per_row_incomes", "per_row_lines"}
        }
        finance = verify_detail_xlsx_finance(pipe["xlsx"], golden_agg)

        audit = json.loads(pipe["audit_path"].read_text(encoding="utf-8"))
        trace_path = Path(str(audit["fifo_trace_file"]))
        trade_id_to_fp = actual.get("trade_id_to_fp") or {}
        trace_rows = read_fifo_trace_rows(trace_path)
        per_line = compare_allocation_lines_to_trace_rows(
            expected_c,
            trace_rows,
            trade_id_to_fp=trade_id_to_fp,
        )

        # CR-10B：合法副本故障注入；觀測值來自本輪正常 UAT（禁固定 True）
        fault_path = runs_case / "fault_cost_income_both_up.xlsx"
        _fault_inject_copy(pipe["xlsx"], fault_path)
        fault_finance = verify_detail_xlsx_finance(fault_path, golden_agg)
        required = resolve_required_outputs(
            audit_json=audit,
            out_dir=out_dir,
            detail_xlsx=fault_path,
            audit_path=pipe["audit_path"],
            exceptions_path=pipe["exc_path"],
        )
        by_type: dict[str, int] = {}
        for a in pipe["match"].allocations:
            by_type[a.match_type] = by_type.get(a.match_type, 0) + a.quantity
        # 正常管線觀測（故障前後不變的項目）
        obs_conservation = bool(audit.get("conservation_ok"))
        art_checks = pipe["artifacts"].get("checks") or {}
        obs_conservation_rows = bool(art_checks.get("conservation_all_rows_ok"))
        obs_artifacts_ok = bool(pipe["artifacts"]["ok"])
        obs_allocated = sum(a.quantity for a in pipe["match"].allocations)
        obs_unsold = sum(u.available for u in pipe["match"].unsold)
        obs_blocking = bool(pipe["match"].blocking)

        # RED-07：以合法報表列序為基線（偵測竄改；非以 D 反推 C 正向答案）
        wb_legit = load_workbook(pipe["xlsx"], data_only=True)
        ws_legit = wb_legit.active
        assert ws_legit is not None
        hdrs = [c.value for c in next(ws_legit.iter_rows(min_row=1, max_row=1))]
        hidx = {h: i for i, h in enumerate(hdrs)}
        legit_costs: list[Decimal] = []
        legit_incomes: list[Decimal] = []
        for row in ws_legit.iter_rows(min_row=2, max_col=len(hdrs), values_only=True):
            if all(v is None for v in row):
                continue
            legit_costs.append(Decimal(str(row[hidx["成本"]] or 0)))
            legit_incomes.append(Decimal(str(row[hidx["收入"]] or 0)))
        golden_rev = {
            **golden_agg,
            "per_row_costs": legit_costs,
            "per_row_incomes": legit_incomes,
        }
        assert verify_detail_xlsx_finance(pipe["xlsx"], golden_rev)["ok"] is True
        per_row_fault = runs_case / "fault_per_row_offset.xlsx"
        _fault_inject_per_row_offset(pipe["xlsx"], per_row_fault)
        per_row_finance = verify_detail_xlsx_finance(per_row_fault, golden_rev)

        # Trace 逐筆故障
        fault_trace = runs_case / "fault_trace_line.xlsx"
        _fault_inject_trace_line(trace_path, fault_trace)
        fault_trace_cmp = compare_allocation_lines_to_trace_rows(
            expected_c,
            read_fifo_trace_rows(fault_trace),
            trade_id_to_fp=trade_id_to_fp,
        )

    fp_after = inv.fingerprint_bundle("phase3_cr10a_after")
    _write_json(run_dir / "formal_fp_after.json", fp_after)
    drift = inv.compare_fingerprint_bundles(fp_before, fp_after)
    _write_json(run_dir / "formal_fp_drift.json", drift)

    # 指紋觀測完成後組裝故障判定（formal_db／conservation 皆為實際觀測）
    obs_formal = drift.get("status") == "PASS"
    fault_checks = build_uat_checks(
        required_outputs=required,
        migration_probe={
            # 本腳本未跑 alembic 探針；不得宣稱 migration 已驗——以 False 顯式排除
            "day_trade_backfill_ok": False,
            "cash_standard_ok": False,
            "foreign_key_check_empty": False,
            "integrity_ok": False,
        },
        fresh_schema_has_match_type=True,  # init_db create_all 本輪已觀測
        allocated_qty=obs_allocated,
        qty_by_match_type=by_type,
        unsold_qty=obs_unsold,
        blocking=obs_blocking,
        conservation_ok=obs_conservation and obs_conservation_rows,
        audit_json=audit,
        integrity_check_result="ok",  # 隔離 UAT DB；正式 DB 另以指紋
        h_annotation_non_interference=True,  # 本輪未重跑 annotation；見 note
        detail_is_draft="DRAFT" in fault_path.name,
        idempotent={
            "old_run_preserved": True,
            "old_run_keys_unchanged": True,
            "new_run_keys_equal_old": True,
            "allocated_qty_same": True,
        },
        formal_db_untouched=bool(obs_formal),
        run_dir_under_data_uat=str(UAT_ROOT.resolve()) in str(run_dir.resolve()),
        out_dir_under_output_uat=str(OUT_ROOT.resolve()) in str(out_dir.resolve()),
        detail_xlsx_finance_ok=bool(fault_finance.get("ok")),
    )
    # 故障路徑不將未執行的 migration／idempotent／annotation-H 當證據；自 checks 移除後再判
    _not_claimed = {
        "actual_migration_day_trade_backfill",
        "actual_migration_cash_standard_ok",
        "actual_migration_fk_ok",
        "actual_migration_integrity_ok",
        "idempotent_old_preserved",
        "idempotent_old_keys_unchanged",
        "idempotent_new_keys_equal",
        "idempotent_qty_same",
        "h_ok",
    }
    fault_checks_claimed = {k: v for k, v in fault_checks.items() if k not in _not_claimed}
    fault_checks_claimed["cr10c_artifacts_ok"] = obs_artifacts_ok
    fault_checks_claimed["conservation_observed_from_audit"] = obs_conservation
    fault_checks_claimed["conservation_rows_ok_observed"] = obs_conservation_rows
    fault_verdict = "PASS" if all(fault_checks_claimed.values()) else "FAIL"
    fault_exit = uat_exit_code(fault_verdict)
    fault_summary = {
        "uat_verdict": fault_verdict,
        "exit_code": fault_exit,
        "failed_checks": [k for k, v in fault_checks_claimed.items() if not v],
        "finance_diffs": fault_finance.get("diffs"),
        "detail_xlsx_finance_ok": fault_finance.get("ok"),
        "observations_from_normal_uat": {
            "conservation_ok": obs_conservation,
            "conservation_rows_ok": obs_conservation_rows,
            "formal_db_untouched": obs_formal,
            "allocated_qty": obs_allocated,
            "artifacts_ok": obs_artifacts_ok,
            "not_claimed_as_evidence": sorted(_not_claimed),
        },
    }
    _write_json(runs_case / "fault_uat_summary.json", fault_summary)

    artifacts = pipe["artifacts"]
    summary.update(
        {
            "finished_at_utc": datetime.now(UTC).isoformat(),
            "import_trade_count": pipe["import_result"].trade_count,
            "detail_xlsx": str(Path(pipe["xlsx"]).relative_to(ROOT)).replace("\\", "/"),
            "detail_is_draft": pipe["detail_is_draft"],
            "open_cost_status": actual.get("open_cost_status"),
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
                "per_row_line_count": len(golden.get("per_row_lines") or []),
            },
            "per_line_trace_vs_c": {
                "ok": per_line["ok"],
                "diffs": per_line["diffs"],
                "errors": per_line["errors"],
                "expected_line_count": per_line["expected_line_count"],
                "actual_matched_count": per_line["actual_matched_count"],
            },
            "cr10c_artifacts": {
                "ok": artifacts["ok"],
                "checks": artifacts["checks"],
                "errors": artifacts["errors"],
            },
            "fault_injection_cr10b": {
                "path": str(fault_path.relative_to(ROOT)).replace("\\", "/"),
                "uat_verdict": fault_verdict,
                "exit_code": fault_exit,
                "failed_checks": fault_summary["failed_checks"],
                "finance_ok": fault_finance.get("ok"),
            },
            "fault_injection_per_row": {
                "path": str(per_row_fault.relative_to(ROOT)).replace("\\", "/"),
                "finance_ok": per_row_finance.get("ok"),
                "diffs": per_row_finance.get("diffs"),
            },
            "fault_injection_trace_line": {
                "path": str(fault_trace.relative_to(ROOT)).replace("\\", "/"),
                "ok": fault_trace_cmp.get("ok"),
                "diffs": fault_trace_cmp.get("diffs"),
            },
            "formal_db_fingerprint": {
                "drift_status": drift.get("status"),
                "untouched": drift.get("status") == "PASS",
            },
            "excel_verification_scope": {
                "mode": "aggregate_primary",
                "per_line_via": "allocation_lines_to_fifo_trace",
                "unverified_fields": [
                    "成交單價（買／賣）逐欄",
                    "備註／annotation 欄",
                    "非聚合明細列順序",
                    "原始 CSV Parser（本腳本僅 HTML bridge）",
                ],
                "note": "不得宣稱 Excel 已全面逐欄驗收；不得從 D 反推 C",
            },
        }
    )
    verdict_ok = (
        compare["ok"]
        and finance["ok"]
        and per_line["ok"]
        and artifacts["ok"]
        and fault_verdict == "FAIL"
        and fault_exit != 0
        and per_row_finance.get("ok") is False
        and fault_trace_cmp.get("ok") is False
        and drift.get("status") == "PASS"
        and not pipe["detail_is_draft"]
        and str(run_dir.resolve()).startswith(str(UAT_ROOT.resolve()))
        and str(out_dir.resolve()).startswith(str(OUT_ROOT.resolve()))
    )
    summary["uat_verdict"] = "PASS" if verdict_ok else "FAIL"
    summary["exit_code"] = uat_exit_code(summary["uat_verdict"])

    _write_json(runs_case / "expected_c_snapshot_meta.json", {
        "case_id": expected_c.get("case_id"),
        "validation_status": expected_c.get("validation_status"),
        "source_integrity": expected_c.get("source_integrity"),
        "aggregates_keys": sorted((expected_c.get("aggregates") or {}).keys()),
        "fifo_expected": expected_c.get("fifo_expected"),
        "realized_status": (expected_c.get("realized_and_open") or {}).get("status"),
        "allocation_count": len(expected_c.get("allocations") or []),
        "allocation_line_count": len(expected_c.get("allocation_lines") or []),
        "note": "完整金額見同目錄 difference／勿 commit",
    })
    _write_json(runs_case / "actual_d.json", {
        k: (str(v) if isinstance(v, Decimal) else v)
        for k, v in actual.items()
        if k not in {"allocation_fingerprints", "trade_fingerprints", "trade_id_to_fp"}
    })
    _write_json(runs_case / "difference.json", {
        "compare_diffs": compare["diffs"],
        "finance_diffs": finance["diffs"],
        "per_line_diffs": per_line["diffs"],
        "fault_cr10b": fault_summary,
        "fault_per_row_caught": per_row_finance.get("ok") is False,
        "fault_trace_caught": fault_trace_cmp.get("ok") is False,
    })
    _write_json(run_dir / "summary.json", summary)
    _write_json(EVIDENCE / "phase03_cr10a_2236_summary.json", {
        k: summary[k]
        for k in (
            "case_id",
            "phase",
            "uat_verdict",
            "exit_code",
            "source_lock_ok",
            "compare_c_d",
            "xlsx_finance_vs_c",
            "per_line_trace_vs_c",
            "cr10c_artifacts",
            "fault_injection_cr10b",
            "fault_injection_per_row",
            "formal_db_fingerprint",
            "started_at_utc",
            "finished_at_utc",
            "runs_d",
        )
        if k in summary
    })
    shutil.copy2(pipe["xlsx"], runs_case / pipe["xlsx"].name)
    shutil.copy2(pipe["audit_path"], runs_case / pipe["audit_path"].name)
    shutil.copy2(trace_path, runs_case / trace_path.name)

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return int(summary["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
