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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _enrich_capital_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        if not item.get("side"):
            item["side"] = r.get("side")
        if not item.get("trade_type"):
            item["trade_type"] = r.get("trade_type") or "CASH"
        if not item.get("currency"):
            item["currency"] = r.get("currency") or "TWD"
        out.append(item)
    return out


def _enrich_parser_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """HTML／玉山分析列僅有 side_raw；轉成 C 層可用列。"""
    out: list[dict[str, Any]] = []
    for idx, r in enumerate(rows):
        item = dict(r)
        raw = str(item.get("side_raw") or "")
        if "買" in raw:
            item["side"] = "BUY"
        elif "賣" in raw:
            item["side"] = "SELL"
        item["trade_type"] = "DAY_TRADE" if "沖" in raw else "CASH"
        item["currency"] = "TWD"
        item["physical_line"] = item.get("row_index", idx + 1)
        # parser 列可能缺 interest
        if "interest" not in item:
            item["interest"] = ""
        out.append(item)
    return out


def build_gold001() -> dict[str, Any]:
    path = inv.SOURCES["csv_2024"]
    analysis = inv.analyze_capital_csv(path)
    rows = _enrich_capital_rows(analysis["rows"])
    sha = sha256_file(path)
    doc = build_expected_c_document(
        case_id="GOLD-001",
        source_sha256=sha,
        source_path=str(path.relative_to(ROOT)).replace("\\", "/"),
        source_format="capital_csv",
        applicable_spec=SPEC_REFS,
        rows=rows,
        opening_lots_policy="NONE_APPROVED",
        known_limitations=[
            "範圍=2024 群益 CSV 單一年度；跨年期初不在本檔",
            f"invalid_row_count={analysis['invalid_row_count']}（CSV 已分計）",
        ],
    )
    doc["row_counts"] = {
        "physical_row_count": analysis["physical_row_count"],
        "valid_trade_count": analysis["valid_trade_count"],
        "excluded_row_count": analysis["excluded_row_count"],
        "invalid_row_count": analysis["invalid_row_count"],
        "symbol_count": analysis["symbol_count"],
        "contains_2236": analysis["contains_2236"],
        "per_symbol_2236": analysis["per_symbol"].get("2236", 0),
    }
    return doc


def build_gold002() -> dict[str, Any]:
    path = inv.SOURCES["capital_xls"]
    analysis = inv.analyze_html_xls(path)
    # analyze_html 未回傳 rows；重跑最小擷取
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
            }
        )
    rows = _enrich_parser_rows(raw_rows)
    # 僅 CASH 進 FIFO；現沖另標
    doc = build_expected_c_document(
        case_id="GOLD-002",
        source_sha256=sha256_file(path),
        source_path=str(path.relative_to(ROOT)).replace("\\", "/"),
        source_format="html_table_xls",
        applicable_spec=SPEC_REFS,
        rows=rows,
        opening_lots_policy="NONE_APPROVED",
        known_limitations=[
            "invalid_row_count=UNKNOWN（HTML 未與 CSV 同等分計）",
            "列擷取沿用 parser 排除語意；非 CR-10 非法分計",
        ],
    )
    doc["row_counts"] = {
        "physical_row_count": analysis["physical_row_count"],
        "valid_trade_count": analysis["valid_trade_count"],
        "excluded_row_count": analysis["excluded_row_count"],
        "invalid_row_count": analysis["invalid_row_count"],
        "symbol_count": analysis["symbol_count"],
        "contains_2236": analysis["contains_2236"],
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
            }
        )
    rows = _enrich_parser_rows(raw_rows)
    doc = build_expected_c_document(
        case_id="GOLD-003",
        source_sha256=sha256_file(path),
        source_path=str(path.relative_to(ROOT)).replace("\\", "/"),
        source_format="esun_xlsx",
        applicable_spec=SPEC_REFS,
        rows=rows,
        opening_lots_policy="NONE_APPROVED",
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
    }
    return doc


def build_gold004() -> dict[str, Any]:
    """四年度 CSV：彙總＋串接 CASH FIFO（無期初；不得偽造）。"""
    csv_keys = ("csv_2023", "csv_2024", "csv_2025", "csv_2026")
    all_rows: list[dict[str, Any]] = []
    per_year: dict[str, Any] = {}
    shas: dict[str, str] = {}
    for key in csv_keys:
        path = inv.SOURCES[key]
        analysis = inv.analyze_capital_csv(path)
        rows = _enrich_capital_rows(analysis["rows"])
        # 保留年度內相對序；跨年以串接順序為 source_order 全域遞增
        for r in rows:
            r = dict(r)
            r["_year_key"] = key
            all_rows.append(r)
        shas[key] = sha256_file(path)
        per_year[key] = {
            "source_sha256": shas[key],
            "valid_trade_count": analysis["valid_trade_count"],
            "invalid_row_count": analysis["invalid_row_count"],
            "excluded_row_count": analysis["excluded_row_count"],
            "physical_row_count": analysis["physical_row_count"],
        }

    # 重新編號 source 序：build 內用 enumerate；列已按年串接
    doc = build_expected_c_document(
        case_id="GOLD-004",
        source_sha256="MULTIPLE",
        source_path="MULTIPLE(see sources[])",
        source_format="capital_csv_multi_year",
        applicable_spec=SPEC_REFS,
        rows=all_rows,
        opening_lots_policy="NONE_APPROVED",
        known_limitations=[
            "多檔 CSV 串接核算；單一 source_sha256 不適用 → 見 sources",
            "無跨年期初核准 lot；檔案起始日前庫存若存在則反映為 unmatched／非完整",
            "不得把 DB 總筆數當 CSV 實體列總和",
        ],
    )
    doc["sources"] = per_year
    doc["source_sha256_by_year"] = shas
    return doc


def main() -> int:
    EXPECTED_C.mkdir(parents=True, exist_ok=True)
    built_at = datetime.now(UTC).isoformat()
    docs = {
        "GOLD-001": build_gold001(),
        "GOLD-002": build_gold002(),
        "GOLD-003": build_gold003(),
        "GOLD-004": build_gold004(),
    }
    for case_id, doc in docs.items():
        doc["built_at_utc"] = built_at
        _write_json(EXPECTED_C / f"{case_id}.json", doc)

    summary = {
        "phase": "2",
        "built_at_utc": built_at,
        "authorization": "Owner PR12 Phase 2 authorized；CR-10A 仍開；Merge／Migration 未授權",
        "cases": {
            cid: {
                "validation_status": d["validation_status"],
                "source_sha256": d.get("source_sha256"),
                "aggregates_valid_trade_count": d["aggregates"]["valid_trade_count"],
                "fifo_unmatched_sell_qty": d["fifo_expected"]["unmatched_sell_qty"],
                "fifo_same_day_reconciled_qty": d["fifo_expected"][
                    "same_day_reconciled_qty"
                ],
                "realized_status": d["realized_and_open"]["status"],
                "invalid_row_count_status": d.get("invalid_row_count_status"),
                "blocking_insufficient_prior_buys": d["fifo_expected"][
                    "blocking_insufficient_prior_buys"
                ],
            }
            for cid, d in docs.items()
        },
        "note": "完整財務答案僅本機 expected_c；公開 Git 僅非敏感程式與文件",
    }
    _write_json(EVIDENCE / "phase02_expected_c_summary.json", summary)

    readme = EXPECTED_C / "README.md"
    readme.write_text(
        "# expected_c\n\n"
        "Phase 2 獨立 C 層財務標準答案（本機）。\n\n"
        "- 推導：A 原始來源＋正式 SPEC（Decimal／Two-Pass／TRUNC／費用第一片段）\n"
        "- 禁止：受測 FIFO／Report Projector／新版 Excel 反推；偽造期初；未知當成功\n"
        "- 公開 Git 不得提交本目錄真實答案 JSON\n",
        encoding="utf-8",
    )

    # 更新 Manifest validation 註記（本機）
    for case_id in docs:
        mpath = MANIFEST_DIR / f"{case_id}.json"
        if not mpath.is_file():
            continue
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
        manifest["expected_c_path"] = f"data/golden/expected_c/{case_id}.json"
        manifest["expected_c_status"] = "INDEPENDENTLY_COMPUTED"
        if case_id in {"GOLD-002", "GOLD-003"}:
            manifest["invalid_row_count"] = inv.unresolved_invalid_row_count(
                "html_table_xls" if case_id == "GOLD-002" else "esun_xlsx"
            )
        _write_json(mpath, manifest)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
