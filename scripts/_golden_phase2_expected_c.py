"""Phase 2：由 A 來源＋SPEC 獨立產出 data/golden/expected_c/（本機；不寫正式 DB）。

禁止：受測 FIFO／Report Projector／新版 Excel 反推；偽造期初；Commit 真實明細。
"""

from __future__ import annotations

import importlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.golden.expected_c import build_expected_c_document

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "data" / "golden"
EXPECTED_C = GOLDEN / "expected_c"
MANIFEST_DIR = GOLDEN / "manifest"
EVIDENCE = GOLDEN / "evidence"

inv = importlib.import_module("scripts._golden_phase01_inventory")
sha256_file = inv.sha256_file

SPEC_REFS = ["docs/spec/SPEC.md §6", "docs/spec/SPEC.md §7"]
ACCOUNT_CAPITAL = "群益_acct_A"
ACCOUNT_ESUN = "esun_acct_A"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _enrich_capital_rows(
    rows: list[dict[str, Any]],
    *,
    source_id: str,
    account_id: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        item["source_id"] = source_id
        item["account_id"] = account_id
        # 不得把未知幣別／類型預設成成功值；沿用 classify 結果
        if item.get("currency") in (None, ""):
            item["currency"] = ""
        if item.get("trade_type") in (None, ""):
            item["trade_type"] = ""
        out.append(item)
    return out


def _enrich_parser_rows(
    rows: list[dict[str, Any]],
    *,
    source_id: str,
    account_id: str,
) -> list[dict[str, Any]]:
    """HTML／玉山分析列僅有 side_raw；轉成 C 層可用列。"""
    out: list[dict[str, Any]] = []
    for idx, r in enumerate(rows):
        item = dict(r)
        item["source_id"] = source_id
        item["account_id"] = account_id
        raw = str(item.get("side_raw") or "")
        if "買" in raw:
            item["side"] = "BUY"
        elif "賣" in raw:
            item["side"] = "SELL"
        if "沖" in raw:
            item["trade_type"] = "DAY_TRADE"
        elif "現股" in raw or raw:
            item["trade_type"] = "CASH"
        else:
            item["trade_type"] = ""
        # HTML／玉山利息常缺 → 空白＝UNKNOWN，不得預設 0 冒充已知
        if "interest" not in item or item.get("interest") is None:
            item["interest"] = ""
        # 幣別：來源未顯式對映時保持空白（UNKNOWN），不硬填 TWD 冒充
        if not item.get("currency"):
            item["currency"] = ""
        item["physical_line"] = item.get("row_index", idx + 1)
        out.append(item)
    return out


def _build_from_capital(
    *,
    case_id: str,
    source_key: str,
    account_id: str,
    rows_filter: Any | None = None,
    extra_limitations: list[str] | None = None,
) -> dict[str, Any]:
    path = inv.SOURCES[source_key]
    analysis = inv.analyze_capital_csv(path)
    gate = inv.csv_acceptance_gate(analysis)
    rows = _enrich_capital_rows(
        analysis["rows"], source_id=source_key, account_id=account_id
    )
    if rows_filter is not None:
        rows = [r for r in rows if rows_filter(r)]
    sha = sha256_file(path)
    expected_sha = {source_key: inv.EXPECTED_SHA256[source_key]}
    actual_sha = {source_key: sha}
    doc = build_expected_c_document(
        case_id=case_id,
        source_sha256=sha,
        source_path=str(path.relative_to(ROOT)).replace("\\", "/"),
        source_format="capital_csv",
        applicable_spec=SPEC_REFS,
        rows=rows,
        opening_lots_policy="NONE_APPROVED",
        expected_source_sha256=expected_sha,
        actual_source_sha256=actual_sha,
        invalid_row_count=analysis["invalid_row_count"],
        known_limitations=[
            f"csv_acceptance_gate={gate['status']}",
            f"invalid_row_count={analysis['invalid_row_count']}（CSV 已分計）",
            *(extra_limitations or []),
        ],
    )
    doc["row_counts"] = {
        "physical_row_count": analysis["physical_row_count"],
        "valid_trade_count": analysis["valid_trade_count"],
        "excluded_row_count": analysis["excluded_row_count"],
        "invalid_row_count": analysis["invalid_row_count"],
        "symbol_count": analysis["symbol_count"],
        "contains_2236": analysis["contains_2236"],
        "scoped_row_count": len(rows),
    }
    doc["csv_acceptance_gate"] = gate
    return doc


def build_gold001() -> dict[str, Any]:
    doc = _build_from_capital(
        case_id="GOLD-001",
        source_key="csv_2024",
        account_id=ACCOUNT_CAPITAL,
        extra_limitations=["範圍=2024 群益 CSV 全檔年度核算"],
    )
    doc["row_counts"]["per_symbol_2236"] = sum(
        1 for r in doc.get("allocations", []) if r.get("symbol") == "2236"
    )
    # 以 analysis per_symbol 為準（上方 scoped）；補回
    path = inv.SOURCES["csv_2024"]
    analysis = inv.analyze_capital_csv(path)
    doc["row_counts"]["per_symbol_2236"] = analysis["per_symbol"].get("2236", 0)
    return doc


def build_gold001_2236() -> dict[str, Any]:
    """GOLD-001 內 2236 九筆獨立答案（由原始 CSV 篩選，非硬編碼數值）。"""
    return _build_from_capital(
        case_id="GOLD-001-2236",
        source_key="csv_2024",
        account_id=ACCOUNT_CAPITAL,
        rows_filter=lambda r: str(r.get("symbol")) == "2236",
        extra_limitations=[
            "範圍=GOLD-001 來源中 symbol=2236 之有效列（預期 9 筆）",
            "數值由 A＋SPEC 獨立核算，非 Reviewer 硬編碼",
        ],
    )


def build_gold002() -> dict[str, Any]:
    path = inv.SOURCES["capital_xls"]
    analysis = inv.analyze_html_xls(path)
    from backend.ingest.html_parser import parse_html_table
    from backend.ingest.mapping import load_profile, map_row
    from backend.ingest.normalizer import should_exclude

    profile = load_profile("statement_html_v1")
    table = parse_html_table(path, profile)
    raw_rows: list[dict[str, Any]] = []
    for row_index, values in table.rows:
        first = values[0].strip() if values else ""
        if should_exclude(first, profile):
            continue
        if not any(str(c).strip() for c in values):
            continue
        mapped = map_row(table.headers, values, profile)
        symbol_name = mapped.get("symbol_and_name", "").strip()
        symbol = symbol_name.split()[0] if symbol_name else ""
        currency_raw = mapped.get("currency_raw", "") or ""
        currency = inv._CAPITAL_CURRENCY_MAP.get(currency_raw, "")
        raw_rows.append(
            {
                "row_index": row_index,
                "symbol": symbol,
                "trade_date": mapped.get("trade_date", ""),
                "side_raw": mapped.get("side_raw", ""),
                "unit_price": mapped.get("unit_price", ""),
                "quantity": mapped.get("quantity", ""),
                "gross_amount": mapped.get("gross_amount", ""),
                "commission": mapped.get("commission", ""),
                "tax": mapped.get("tax", ""),
                "net_settlement": mapped.get("net_settlement", ""),
                "interest": mapped.get("interest", "") or "",
                "currency": currency,
                "currency_raw": currency_raw,
            }
        )
    rows = _enrich_parser_rows(
        raw_rows, source_id="capital_xls", account_id=ACCOUNT_CAPITAL
    )
    # HTML 無幣別時無法進 CASH FIFO；若全空則標記 PARTIAL（不硬填 TWD）
    sha = sha256_file(path)
    doc = build_expected_c_document(
        case_id="GOLD-002",
        source_sha256=sha,
        source_path=str(path.relative_to(ROOT)).replace("\\", "/"),
        source_format="html_table_xls",
        applicable_spec=SPEC_REFS,
        rows=rows,
        opening_lots_policy="NONE_APPROVED",
        expected_source_sha256={"capital_xls": inv.EXPECTED_SHA256["capital_xls"]},
        actual_source_sha256={"capital_xls": sha},
        invalid_row_count=analysis["invalid_row_count"],
        known_limitations=[
            "invalid_row_count=UNKNOWN（HTML 未與 CSV 同等分計）",
            "列擷取沿用 parser 排除語意；非 CR-10 非法分計",
            "幣別／利息缺欄保持 UNKNOWN，不預設成功",
        ],
    )
    doc["row_counts"] = {
        "physical_row_count": analysis["physical_row_count"],
        "valid_trade_count": analysis["valid_trade_count"],
        "excluded_row_count": analysis["excluded_row_count"],
        "invalid_row_count": analysis["invalid_row_count"],
        "symbol_count": analysis["symbol_count"],
        "contains_2236": analysis["contains_2236"],
        "scoped_row_count": len(rows),
    }
    return doc


def build_gold003() -> dict[str, Any]:
    path = inv.SOURCES["esun_xlsx"]
    analysis = inv.analyze_esun_xlsx(path)
    from backend.ingest.esun_xlsx_parser import parse_esun_xlsx
    from backend.ingest.mapping import load_profile, map_row
    from backend.ingest.normalizer import should_exclude

    profile = load_profile("esun_xlsx_v1")
    table = parse_esun_xlsx(path, profile)
    raw_rows: list[dict[str, Any]] = []
    for row_index, values in table.rows:
        first = values[0].strip() if values else ""
        if should_exclude(first, profile):
            continue
        mapped = map_row(table.headers, values, profile)
        currency_raw = mapped.get("currency_raw", "") or mapped.get("currency", "") or ""
        currency = inv._CAPITAL_CURRENCY_MAP.get(str(currency_raw), "")
        raw_rows.append(
            {
                "row_index": row_index,
                "symbol": mapped.get("symbol", "").strip(),
                "trade_date": mapped.get("trade_date", ""),
                "side_raw": mapped.get("side_raw", ""),
                "unit_price": mapped.get("unit_price", ""),
                "quantity": mapped.get("quantity", ""),
                "gross_amount": mapped.get("gross_amount", ""),
                "commission": mapped.get("commission", ""),
                "tax": mapped.get("tax", ""),
                "net_settlement": mapped.get("net_settlement", ""),
                "interest": mapped.get("interest", "") or "",
                "currency": currency,
                "currency_raw": currency_raw,
            }
        )
    rows = _enrich_parser_rows(
        raw_rows, source_id="esun_xlsx", account_id=ACCOUNT_ESUN
    )
    sha = sha256_file(path)
    doc = build_expected_c_document(
        case_id="GOLD-003",
        source_sha256=sha,
        source_path=str(path.relative_to(ROOT)).replace("\\", "/"),
        source_format="esun_xlsx",
        applicable_spec=SPEC_REFS,
        rows=rows,
        opening_lots_policy="NONE_APPROVED",
        expected_source_sha256={"esun_xlsx": inv.EXPECTED_SHA256["esun_xlsx"]},
        actual_source_sha256={"esun_xlsx": sha},
        invalid_row_count=analysis["invalid_row_count"],
        extra_fields_not_computable=[
            "opening_lots_for_2236_and_other_sell_only",
        ],
        known_limitations=[
            "invalid_row_count=UNKNOWN",
            "2236 缺買進：FIFO 預期出現 unmatched；不得混配群益或自造期初",
            "未平倉／已實現對缺買進賣出不得以 0 冒充完整成功",
        ],
    )
    doc["row_counts"] = {
        "physical_row_count": analysis["physical_row_count"],
        "valid_trade_count": analysis["valid_trade_count"],
        "excluded_row_count": analysis["excluded_row_count"],
        "invalid_row_count": analysis["invalid_row_count"],
        "symbol_count": analysis["symbol_count"],
        "contains_2236": analysis["contains_2236"],
        "symbol_2236_side_note": "SELL_ONLY_NO_BUY_PENDING_OPENING",
        "scoped_row_count": len(rows),
    }
    return doc


def build_gold004() -> dict[str, Any]:
    """四年度 CSV：彙總＋串接 CASH FIFO；trade_id＝source_id:L列號。"""
    csv_keys = ("csv_2023", "csv_2024", "csv_2025", "csv_2026")
    all_rows: list[dict[str, Any]] = []
    per_year: dict[str, Any] = {}
    shas: dict[str, str] = {}
    expected_sha: dict[str, str] = {}
    invalid_total = 0
    gate_failures: list[str] = []
    for key in csv_keys:
        path = inv.SOURCES[key]
        analysis = inv.analyze_capital_csv(path)
        gate = inv.csv_acceptance_gate(analysis)
        if gate["status"] != "PASS":
            gate_failures.append(f"{key}:{gate['status']}:{gate.get('reason')}")
        rows = _enrich_capital_rows(
            analysis["rows"], source_id=key, account_id=ACCOUNT_CAPITAL
        )
        all_rows.extend(rows)
        shas[key] = sha256_file(path)
        expected_sha[key] = inv.EXPECTED_SHA256[key]
        invalid_total += int(analysis["invalid_row_count"])
        per_year[key] = {
            "source_sha256": shas[key],
            "valid_trade_count": analysis["valid_trade_count"],
            "invalid_row_count": analysis["invalid_row_count"],
            "excluded_row_count": analysis["excluded_row_count"],
            "physical_row_count": analysis["physical_row_count"],
            "csv_acceptance_gate": gate["status"],
        }

    doc = build_expected_c_document(
        case_id="GOLD-004",
        source_sha256="MULTIPLE",
        source_path="MULTIPLE(see sources[])",
        source_format="capital_csv_multi_year",
        applicable_spec=SPEC_REFS,
        rows=all_rows,
        opening_lots_policy="NONE_APPROVED",
        expected_source_sha256=expected_sha,
        actual_source_sha256=shas,
        invalid_row_count=invalid_total,
        known_limitations=[
            "多檔 CSV 串接；trade_id=source_id:L{physical_line} 全域唯一",
            "無跨年期初核准 lot；不得偽造期初",
            "不得把 DB 總筆數當 CSV 實體列總和",
            *( [f"gate_failures={gate_failures}"] if gate_failures else [] ),
        ],
    )
    doc["sources"] = per_year
    doc["source_sha256_by_year"] = shas
    doc["trade_id_unique"] = doc.get("trade_id_unique")
    return doc


def main() -> int:
    EXPECTED_C.mkdir(parents=True, exist_ok=True)
    built_at = datetime.now(UTC).isoformat()
    docs = {
        "GOLD-001": build_gold001(),
        "GOLD-001-2236": build_gold001_2236(),
        "GOLD-002": build_gold002(),
        "GOLD-003": build_gold003(),
        "GOLD-004": build_gold004(),
    }
    for case_id, doc in docs.items():
        doc["built_at_utc"] = built_at
        _write_json(EXPECTED_C / f"{case_id}.json", doc)

    summary = {
        "phase": "2_r2",
        "built_at_utc": built_at,
        "authorization": (
            "Owner PR12 Phase 2 複審修正；CR-10A 仍開；Merge／Migration 未授權"
        ),
        "cases": {
            cid: {
                "validation_status": d["validation_status"],
                "source_integrity": d.get("source_integrity", {}).get("status"),
                "fifo_scope": d.get("fifo_scope"),
                "trade_id_unique": d.get("trade_id_unique"),
                "allocation_count": len(d.get("allocations") or []),
                "allocation_line_count": len(d.get("allocation_lines") or []),
                "aggregates_valid_trade_count": d["aggregates"]["valid_trade_count"],
                "fifo_unmatched_sell_qty": d["fifo_expected"]["unmatched_sell_qty"],
                "realized_status": d["realized_and_open"]["status"],
                "invalid_row_count": d.get("invalid_row_count"),
            }
            for cid, d in docs.items()
        },
        "note": "完整財務答案／逐筆 allocation 僅本機 expected_c；公開 Git 僅非敏感程式與文件",
    }
    _write_json(EVIDENCE / "phase02_expected_c_summary.json", summary)

    readme = EXPECTED_C / "README.md"
    readme.write_text(
        "# expected_c\n\n"
        "Phase 2 獨立 C 層財務標準答案（本機）。\n\n"
        "- 推導：A 原始來源＋正式 SPEC（Decimal／Two-Pass／TRUNC／費用第一片段）\n"
        "- trade_id：`{source_id}:L{physical_line}` 全域唯一\n"
        "- 含逐筆 allocations／allocation_lines（成本／收入／費用落點／價金尾差）\n"
        "- 來源 SHA256 鎖定或非法列失敗 → 不得標完整成功\n"
        "- 公開 Git 不得提交本目錄真實答案 JSON\n",
        encoding="utf-8",
    )

    for case_id, doc in docs.items():
        # Manifest 僅更新 GOLD-001～004 主檔；2236 子案另記
        base = "GOLD-001" if case_id.startswith("GOLD-001") else case_id
        mpath = MANIFEST_DIR / f"{base}.json"
        if not mpath.is_file():
            continue
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
        if case_id == "GOLD-001-2236":
            manifest["expected_c_2236_path"] = "data/golden/expected_c/GOLD-001-2236.json"
            manifest["expected_c_2236_status"] = doc["validation_status"]
        else:
            manifest["expected_c_path"] = f"data/golden/expected_c/{case_id}.json"
            manifest["expected_c_status"] = doc["validation_status"]
        if case_id in {"GOLD-002", "GOLD-003"}:
            manifest["invalid_row_count"] = inv.unresolved_invalid_row_count(
                "html_table_xls" if case_id == "GOLD-002" else "esun_xlsx"
            )
        _write_json(mpath, manifest)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
