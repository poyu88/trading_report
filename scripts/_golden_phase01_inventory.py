"""Phase 0+1 黃金驗收盤點腳本（唯讀；不寫正式 DB）。

產出 data/golden/ 下 Manifest、evidence、baseline 索引。
禁止：init_db／apply_import／migration／寫入 trading.db。
"""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.util.date_text import date_bounds, format_manifest_date
from backend.util.sha256_lock import sha256_lock_mismatches

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "data" / "golden"
EVIDENCE = GOLDEN / "evidence"
MANIFEST_DIR = GOLDEN / "manifest"
SOURCE_A = GOLDEN / "source_a"
BASELINE_B = GOLDEN / "baseline_b"
EXPECTED_C = GOLDEN / "expected_c"
RUNS_D = GOLDEN / "runs_d"
MUTATIONS = GOLDEN / "mutations"

SOURCES: dict[str, Path] = {
    "capital_xls": ROOT / "input" / "群益.xls",
    "esun_xlsx": ROOT / "input" / "玉山.xlsx",
    "csv_2024": ROOT
    / "data"
    / "source_archive"
    / "c9fd353546b961e0b281c929e38bc157d96bf3a2d4eaa691e9ce9cdde67cb737.csv",
    "csv_2023": ROOT
    / "data"
    / "source_archive"
    / "2479918089261a25dd85fcaa06886ec459e3e4e6a6ba63eefc59891ae6b381cb.csv",
    "csv_2025": ROOT
    / "data"
    / "source_archive"
    / "047827e12418f4af1a660b5007baa753fa830ea2bdb6359cfe5d6e45188d4a86.csv",
    "csv_2026": ROOT
    / "data"
    / "source_archive"
    / "67ef3a325528364466f7b3b4ec0340965eba52177f894e4ead6b4f18792f6f28.csv",
    "trading_db": ROOT / "data" / "trading.db",
}

EXPECTED_SHA256: dict[str, str] = {
    "capital_xls": "1b8762b073b1a0b543efb15f1c3f5612e2009150a9f9041cae461d53519f1e13",
    "esun_xlsx": "6bb26e7317b2f629aa862a4e62771db9f6e7bc5abcbf7905227267ad99e0d2cf",
    "csv_2024": "c9fd353546b961e0b281c929e38bc157d96bf3a2d4eaa691e9ce9cdde67cb737",
    "csv_2023": "2479918089261a25dd85fcaa06886ec459e3e4e6a6ba63eefc59891ae6b381cb",
    "csv_2025": "047827e12418f4af1a660b5007baa753fa830ea2bdb6359cfe5d6e45188d4a86",
    "csv_2026": "67ef3a325528364466f7b3b4ec0340965eba52177f894e4ead6b4f18792f6f28",
    "trading_db": "07ffcde9e0863a688ce8aa63a7079e2b43d50dfae71e3a020817044cd980edbb",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def file_meta(path: Path) -> dict[str, Any]:
    st = path.stat()
    return {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "exists": True,
        "file_size_bytes": st.st_size,
        "mtime_utc": datetime.fromtimestamp(st.st_mtime, tz=UTC).isoformat(),
        "sha256": sha256_file(path),
    }


def fingerprint_bundle(label: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "label": label,
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "files": {},
        "wal_shm_note": (
            "trading.db 可能伴隨 -wal/-shm；本盤點對主檔 trading.db 算 SHA256。"
            "若有 open connection 寫入，指紋可能變動；本腳本僅 URI mode=ro 查詢。"
        ),
    }
    for key, path in SOURCES.items():
        if not path.is_file():
            out["files"][key] = {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "exists": False,
                "sha256": None,
                "file_size_bytes": None,
                "mtime_utc": None,
            }
            continue
        meta = file_meta(path)
        expected = EXPECTED_SHA256.get(key)
        meta["matches_plan_expected"] = (
            expected is not None and meta["sha256"] == expected
        )
        meta["plan_expected_sha256"] = expected
        if key == "trading_db":
            for suffix in ("-wal", "-shm"):
                side = path.with_name(path.name + suffix)
                if side.is_file():
                    sm = file_meta(side)
                    meta[f"sidecar{suffix}"] = {
                        "sha256": sm["sha256"],
                        "file_size_bytes": sm["file_size_bytes"],
                        "mtime_utc": sm["mtime_utc"],
                    }
                else:
                    meta[f"sidecar{suffix}"] = None
        out["files"][key] = meta
    return out


def open_db_ro() -> sqlite3.Connection:
    db = SOURCES["trading_db"].resolve()
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def analyze_capital_csv(path: Path) -> dict[str, Any]:
    """群益年度 CSV：第 1 列欄位名、第 2 列延續表頭、其後資料、結尾總合。"""
    text = path.read_text(encoding="utf-8-sig")
    physical_lines = text.splitlines()
    physical_row_count = len(physical_lines)

    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))

    header_row_count = 0
    data_start = 0
    if rows:
        header_row_count = 1
        data_start = 1
        # 第二列常為空商品＋延續表頭字樣
        if len(rows) > 1:
            first = (rows[1][0] if rows[1] else "").strip()
            if first == "" or "擔保" in "".join(rows[1]):
                header_row_count = 2
                data_start = 2

    valid: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    blank = 0
    for i, row in enumerate(rows[data_start:], start=data_start + 1):
        if not any(str(c).strip() for c in row):
            blank += 1
            continue
        first = (row[0] if row else "").strip()
        if first.startswith("總合"):
            excluded.append({"physical_line": i, "reason": "total_row", "first_cell": first})
            continue
        # symbol = first token before space
        symbol = first.split()[0] if first else ""
        side_raw = row[2].strip() if len(row) > 2 else ""
        trade_date = row[1].strip() if len(row) > 1 else ""
        valid.append(
            {
                "physical_line": i,
                "symbol": symbol,
                "name_cell": first,
                "trade_date": trade_date,
                "side_raw": side_raw,
                "unit_price": row[4].strip() if len(row) > 4 else "",
                "quantity": row[5].strip() if len(row) > 5 else "",
                "gross_amount": row[6].strip() if len(row) > 6 else "",
                "commission": row[7].strip() if len(row) > 7 else "",
                "tax": row[8].strip() if len(row) > 8 else "",
                "net_settlement": row[9].strip() if len(row) > 9 else "",
                "interest": row[12].strip() if len(row) > 12 else "",
            }
        )

    # duplicate detection: exact key of business fields
    keys = [
        (
            r["symbol"],
            r["trade_date"],
            r["side_raw"],
            r["unit_price"],
            r["quantity"],
            r["gross_amount"],
            r["commission"],
            r["tax"],
            r["net_settlement"],
        )
        for r in valid
    ]
    key_counts = Counter(keys)
    duplicate_row_count = sum(c - 1 for c in key_counts.values() if c > 1)
    per_symbol = Counter(r["symbol"] for r in valid)

    dates = [r["trade_date"] for r in valid if r["trade_date"]]
    d_from, d_to = date_bounds(dates)

    return {
        "source_path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "physical_row_count": physical_row_count,
        "csv_reader_row_count": len(rows),
        "header_row_count": header_row_count,
        "blank_data_region_rows": blank,
        "valid_trade_count": len(valid),
        "excluded_row_count": len(excluded),
        "excluded_rows": excluded,
        "duplicate_row_count": duplicate_row_count,
        "symbol_count": len(per_symbol),
        "per_symbol": dict(sorted(per_symbol.items())),
        "contains_2236": "2236" in per_symbol,
        "date_from": format_manifest_date(d_from),
        "date_to": format_manifest_date(d_to),
        "rows": valid,
    }


def analyze_html_xls(path: Path) -> dict[str, Any]:
    """群益 .xls 實際為 HTML table。"""
    from backend.ingest.html_parser import parse_html_table
    from backend.ingest.mapping import load_profile, map_row
    from backend.ingest.normalizer import should_exclude

    profile = load_profile("statement_html_v1")
    raw_bytes = path.read_bytes()
    # physical "rows" for HTML: count <tr>
    tr_count = raw_bytes.lower().count(b"<tr")
    table = parse_html_table(path, profile)
    header_row_count = 1  # parser consumes header separately
    valid: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for row_index, values in table.rows:
        first = values[0].strip() if values else ""
        reason = should_exclude(first, profile)
        if reason:
            excluded.append(
                {"row_index": row_index, "reason": reason, "first_cell": first}
            )
            continue
        if not any(str(c).strip() for c in values):
            continue
        mapped = map_row(table.headers, values, profile)
        symbol_name = mapped.get("symbol_and_name", "").strip()
        symbol = symbol_name.split()[0] if symbol_name else ""
        valid.append(
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
                "interest": mapped.get("interest", ""),
            }
        )

    keys = [
        (
            r["symbol"],
            r["trade_date"],
            r["side_raw"],
            r["unit_price"],
            r["quantity"],
            r["gross_amount"],
            r["commission"],
            r["tax"],
            r["net_settlement"],
        )
        for r in valid
    ]
    key_counts = Counter(keys)
    duplicate_row_count = sum(c - 1 for c in key_counts.values() if c > 1)
    per_symbol = Counter(r["symbol"] for r in valid)
    dates = [r["trade_date"] for r in valid if r["trade_date"]]
    d_from, d_to = date_bounds(dates)

    return {
        "source_path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "source_format": "html_table_xls",
        "physical_tr_count": tr_count,
        "parser_data_row_count": len(table.rows),
        "header_row_count": header_row_count,
        "valid_trade_count": len(valid),
        "excluded_row_count": len(excluded),
        "excluded_rows": excluded,
        "duplicate_row_count": duplicate_row_count,
        "symbol_count": len(per_symbol),
        "per_symbol": dict(sorted(per_symbol.items())),
        "contains_2236": "2236" in per_symbol,
        "date_from": format_manifest_date(d_from),
        "date_to": format_manifest_date(d_to),
        "parser_profile": "statement_html_v1",
        "parser_version": profile.version,
        "physical_row_count_note": (
            "HTML-xls 無純文字列概念；physical_tr_count=原始 <tr> 數；"
            "valid_trade_count=parser 後非排除列。"
        ),
        "physical_row_count": tr_count,
    }


def analyze_esun_xlsx(path: Path) -> dict[str, Any]:
    from openpyxl import load_workbook

    from backend.ingest.esun_xlsx_parser import parse_esun_xlsx
    from backend.ingest.mapping import load_profile, map_row
    from backend.ingest.normalizer import should_exclude

    profile = load_profile("esun_xlsx_v1")
    wb = load_workbook(path, data_only=True, read_only=True)
    ws = wb.active
    physical_row_count = 0
    if ws is not None:
        for _ in ws.iter_rows():
            physical_row_count += 1
    wb.close()

    table = parse_esun_xlsx(path, profile)
    valid: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for row_index, values in table.rows:
        first = values[0].strip() if values else ""
        reason = should_exclude(first, profile)
        if reason:
            excluded.append(
                {"row_index": row_index, "reason": reason, "first_cell": first}
            )
            continue
        mapped = map_row(table.headers, values, profile)
        symbol = mapped.get("symbol", "").strip()
        valid.append(
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
                "interest": mapped.get("interest", ""),
            }
        )

    keys = [
        (
            r["symbol"],
            r["trade_date"],
            r["side_raw"],
            r["unit_price"],
            r["quantity"],
            r["gross_amount"],
            r["commission"],
            r["tax"],
            r["net_settlement"],
        )
        for r in valid
    ]
    key_counts = Counter(keys)
    duplicate_row_count = sum(c - 1 for c in key_counts.values() if c > 1)
    per_symbol = Counter(r["symbol"] for r in valid)
    dates = [r["trade_date"] for r in valid if r["trade_date"]]
    d_from, d_to = date_bounds(dates)

    return {
        "source_path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "source_format": "esun_xlsx",
        "physical_row_count": physical_row_count,
        "parser_data_row_count": len(table.rows),
        "header_row_count": "UNKNOWN",  # esun parser 內部找表頭；未對外暴露
        "valid_trade_count": len(valid),
        "excluded_row_count": len(excluded),
        "excluded_rows": excluded,
        "duplicate_row_count": duplicate_row_count,
        "symbol_count": len(per_symbol),
        "per_symbol": dict(sorted(per_symbol.items())),
        "contains_2236": "2236" in per_symbol,
        "date_from": format_manifest_date(d_from),
        "date_to": format_manifest_date(d_to),
        "parser_profile": "esun_xlsx_v1",
        "parser_version": profile.version,
        "known_limitations": [
            "header_row_count 對玉山 parser 未對外暴露 → UNKNOWN",
            "2236 若缺買進不得與群益混配、不得自造期初（Owner 決策）",
        ],
    }


def normalize_qty(text: str) -> str:
    return text.replace(",", "").strip()


def normalize_num(text: str) -> str:
    """正規化金額／單價字串（委派 ``backend.util.decimal_text``）。

    非法數值回傳唯一 sentinel（含原文摘要），使交叉核對無法誤判為相等
    （GOLD-CR-06 fail-closed）。
    """
    from backend.util.decimal_text import normalize_decimal_text

    try:
        return normalize_decimal_text(text)
    except ValueError:
        return f"__INVALID_DECIMAL__:{text!r}"


def inventory_exit_code(*, blockers: list[str], inv_fail: bool) -> int:
    """GOLD-CR-09：有阻礙或 INV 失敗 → 非零結束碼。"""
    if blockers or inv_fail:
        return 1
    return 0


def side_to_buy_sell(side_raw: str) -> str:
    if "買" in side_raw:
        return "BUY"
    if "賣" in side_raw:
        return "SELL"
    return "UNKNOWN"


def db_inventory(con: sqlite3.Connection) -> dict[str, Any]:
    brokers = [dict(r) for r in con.execute(
        "SELECT b.id AS broker_id, b.name AS broker_name, a.id AS account_id, "
        "a.account_label FROM accounts a JOIN brokers b ON b.id=a.broker_id"
    )]
    batches = []
    for r in con.execute(
        "SELECT id, account_id, filename, file_sha256, profile_id, profile_version, "
        "status, archive_path, imported_at_utc FROM import_batches ORDER BY imported_at_utc"
    ):
        d = dict(r)
        stats = con.execute(
            "SELECT "
            "(SELECT COUNT(*) FROM raw_rows WHERE batch_id=?) AS raw_count, "
            "(SELECT COUNT(*) FROM raw_rows WHERE batch_id=? AND parse_status='ok') AS raw_ok, "
            "(SELECT COUNT(*) FROM raw_rows rr JOIN trades t ON t.raw_row_id=rr.id "
            " WHERE rr.batch_id=?) AS trade_count",
            (d["id"], d["id"], d["id"]),
        ).fetchone()
        d["raw_count"] = stats["raw_count"]
        d["raw_ok"] = stats["raw_ok"]
        d["trade_count"] = stats["trade_count"]
        # parse_status breakdown
        statuses = {
            row["parse_status"]: row["c"]
            for row in con.execute(
                "SELECT parse_status, COUNT(*) c FROM raw_rows WHERE batch_id=? "
                "GROUP BY parse_status",
                (d["id"],),
            )
        }
        d["parse_status_counts"] = statuses
        batches.append(d)

    trade_total = con.execute("SELECT COUNT(*) c FROM trades").fetchone()["c"]
    raw_total = con.execute("SELECT COUNT(*) c FROM raw_rows").fetchone()["c"]
    per_symbol = {
        row["symbol"]: row["c"]
        for row in con.execute(
            "SELECT symbol, COUNT(*) c FROM trades GROUP BY symbol ORDER BY symbol"
        )
    }
    per_side = {
        row["side"]: row["c"]
        for row in con.execute("SELECT side, COUNT(*) c FROM trades GROUP BY side")
    }
    # schema columns for cross-check notes
    trade_cols = [
        r[1] for r in con.execute("PRAGMA table_info(trades)").fetchall()
    ]
    raw_cols = [
        r[1] for r in con.execute("PRAGMA table_info(raw_rows)").fetchall()
    ]
    return {
        "brokers_accounts": brokers,
        "batches": batches,
        "trade_total": trade_total,
        "raw_total": raw_total,
        "per_symbol": per_symbol,
        "per_side": per_side,
        "schema": {"trades": trade_cols, "raw_rows": raw_cols},
    }


def cross_check_csv_to_db(
    csv_analysis: dict[str, Any],
    con: sqlite3.Connection,
    *,
    file_sha256: str,
    symbol_filter: str | None = None,
) -> dict[str, Any]:
    """CSV 有效列 ↔ DB trades（依 batch.file_sha256）逐欄交叉。

    TODO(GOLD-CR-05): 來源端外部 trade id 齊全後擴充交叉鍵；缺則維持 NOT_IN_SOURCE。
    TODO(GOLD-CR-11): 多帳戶／批次歧義樣本齊全後禁止任意選 batch。
    """
    batch = con.execute(
        "SELECT * FROM import_batches WHERE file_sha256=?",
        (file_sha256,),
    ).fetchone()
    if batch is None:
        return {
            "status": "FAIL",
            "reason": "no_import_batch_for_sha256",
            "file_sha256": file_sha256,
            "csv_valid_trade_count": csv_analysis["valid_trade_count"],
        }

    batch_id = batch["id"]
    db_rows = [
        dict(r)
        for r in con.execute(
            "SELECT t.id AS trade_id, t.raw_row_id, t.symbol, t.name, t.trade_date, "
            "t.side, t.quantity, t.unit_price_txt, t.gross_amount_txt, "
            "t.commission_txt, t.tax_txt, t.interest_txt, t.net_settlement_txt, "
            "rr.row_index, rr.row_sha256, rr.parse_status, rr.error_code "
            "FROM trades t "
            "JOIN raw_rows rr ON rr.id=t.raw_row_id "
            "WHERE rr.batch_id=? "
            "ORDER BY rr.row_index",
            (batch_id,),
        )
    ]
    if symbol_filter:
        db_rows = [r for r in db_rows if r["symbol"] == symbol_filter]

    csv_rows = csv_analysis["rows"]
    if symbol_filter:
        csv_rows = [r for r in csv_rows if r["symbol"] == symbol_filter]

    # Match by (symbol, trade_date, side, qty, unit_price, gross, commission, tax)
    def csv_key(r: dict[str, Any]) -> tuple[Any, ...]:
        return (
            r["symbol"],
            r["trade_date"].replace("-", "/"),
            side_to_buy_sell(r["side_raw"]),
            normalize_qty(r["quantity"]),
            normalize_num(r["unit_price"]),
            normalize_num(r["gross_amount"]),
            normalize_num(r["commission"]),
            normalize_num(r["tax"]),
            normalize_num(r["net_settlement"]),
        )

    def db_key(r: dict[str, Any]) -> tuple[Any, ...]:
        td = r["trade_date"].replace("-", "/")
        # DB may store YYYY-MM-DD
        if len(td) == 10 and td[4] == "-":
            y, m, d = td.split("-")
            td = f"{y}/{int(m)}/{int(d)}"
        # normalize date: CSV uses 2024/8/5, DB might be 2024-08-05
        parts = td.replace("-", "/").split("/")
        if len(parts) == 3:
            td = f"{int(parts[0])}/{int(parts[1])}/{int(parts[2])}"
        return (
            r["symbol"],
            td,
            r["side"],
            str(r["quantity"]),
            normalize_num(r["unit_price_txt"]),
            normalize_num(r["gross_amount_txt"]),
            normalize_num(r["commission_txt"]),
            normalize_num(r["tax_txt"]),
            normalize_num(r["net_settlement_txt"] or ""),
        )

    # Also normalize CSV dates
    def csv_key_norm(r: dict[str, Any]) -> tuple[Any, ...]:
        k = list(csv_key(r))
        parts = str(k[1]).replace("-", "/").split("/")
        if len(parts) == 3:
            k[1] = f"{int(parts[0])}/{int(parts[1])}/{int(parts[2])}"
        return tuple(k)

    csv_pool: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for r in csv_rows:
        csv_pool.setdefault(csv_key_norm(r), []).append(r)

    matches: list[dict[str, Any]] = []
    unmatched_db: list[dict[str, Any]] = []
    for dr in db_rows:
        k = db_key(dr)
        pool = csv_pool.get(k)
        if pool:
            cr = pool.pop(0)
            field_cmp = {
                "symbol": {"csv": cr["symbol"], "db": dr["symbol"], "ok": cr["symbol"] == dr["symbol"]},
                "trade_date": {"csv": cr["trade_date"], "db": dr["trade_date"], "ok": True},
                "side": {
                    "csv": cr["side_raw"],
                    "db": dr["side"],
                    "ok": side_to_buy_sell(cr["side_raw"]) == dr["side"],
                },
                "quantity": {
                    "csv": cr["quantity"],
                    "db": dr["quantity"],
                    "ok": normalize_qty(cr["quantity"]) == str(dr["quantity"]),
                },
                "unit_price": {
                    "csv": cr["unit_price"],
                    "db": dr["unit_price_txt"],
                    "ok": normalize_num(cr["unit_price"])
                    == normalize_num(dr["unit_price_txt"]),
                },
                "gross_amount": {
                    "csv": cr["gross_amount"],
                    "db": dr["gross_amount_txt"],
                    "ok": normalize_num(cr["gross_amount"])
                    == normalize_num(dr["gross_amount_txt"]),
                },
                "commission": {
                    "csv": cr["commission"],
                    "db": dr["commission_txt"],
                    "ok": normalize_num(cr["commission"])
                    == normalize_num(dr["commission_txt"]),
                },
                "tax": {
                    "csv": cr["tax"],
                    "db": dr["tax_txt"],
                    "ok": normalize_num(cr["tax"]) == normalize_num(dr["tax_txt"]),
                },
                "interest": {
                    "csv": cr.get("interest", ""),
                    "db": dr["interest_txt"],
                    "ok": normalize_num(cr.get("interest", "") or "0")
                    == normalize_num(dr["interest_txt"] or "0"),
                },
                "net_settlement": {
                    "csv": cr["net_settlement"],
                    "db": dr["net_settlement_txt"],
                    "ok": normalize_num(cr["net_settlement"])
                    == normalize_num(dr["net_settlement_txt"] or ""),
                },
                "raw_row_id": {"csv": "NOT_IN_SOURCE", "db": dr["raw_row_id"], "ok": None},
                "trade_id": {"csv": "NOT_IN_SOURCE", "db": dr["trade_id"], "ok": None},
                "import_batch_id": {"csv": "NOT_IN_SOURCE", "db": batch_id, "ok": None},
                "row_sha256": {"csv": "NOT_IN_SOURCE", "db": dr["row_sha256"], "ok": None},
                "csv_physical_line": cr["physical_line"],
                "db_row_index": dr["row_index"],
            }
            all_ok = all(
                v["ok"] is True
                for k2, v in field_cmp.items()
                if isinstance(v, dict) and "ok" in v and v["ok"] is not None
            )
            matches.append(
                {
                    "match_ok": all_ok,
                    "csv_physical_line": cr["physical_line"],
                    "db_row_index": dr["row_index"],
                    "trade_id": dr["trade_id"],
                    "raw_row_id": dr["raw_row_id"],
                    "fields": field_cmp,
                }
            )
        else:
            unmatched_db.append(
                {
                    "trade_id": dr["trade_id"],
                    "raw_row_id": dr["raw_row_id"],
                    "row_index": dr["row_index"],
                    "key": list(k),
                }
            )

    unmatched_csv = []
    for k, pool in csv_pool.items():
        for cr in pool:
            unmatched_csv.append(
                {
                    "physical_line": cr["physical_line"],
                    "key": list(k),
                }
            )

    status = "PASS"
    if unmatched_csv or unmatched_db or any(not m["match_ok"] for m in matches):
        status = "FAIL"
    # count mismatch may already be FAIL via unmatched
    if status == "PASS" and (
        len(matches) != len(csv_rows)
        or len(matches) != len(db_rows)
        or len(csv_rows) != len(db_rows)
    ):
        status = "FAIL"

    return {
        "status": status,
        "file_sha256": file_sha256,
        "batch_id": batch_id,
        "batch_filename": batch["filename"],
        "batch_profile_id": batch["profile_id"],
        "batch_profile_version": batch["profile_version"],
        "symbol_filter": symbol_filter,
        "csv_valid_trade_count": len(csv_rows),
        "db_trade_count": len(db_rows),
        "matched_count": len(matches),
        "field_mismatch_count": sum(1 for m in matches if not m["match_ok"]),
        "unmatched_csv_count": len(unmatched_csv),
        "unmatched_db_count": len(unmatched_db),
        "unmatched_csv": unmatched_csv,
        "unmatched_db": unmatched_db,
        "matches": matches,
        "field_coverage_notes": {
            "csv_has_raw_row_id": False,
            "csv_has_trade_id": False,
            "csv_has_import_batch": False,
            "csv_has_row_sha256": False,
            "marked_as": "NOT_IN_SOURCE",
        },
    }


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def strip_rows_for_public(analysis: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in analysis.items() if k != "rows"}
    return out


def build_manifest(case_id: str, **fields: Any) -> dict[str, Any]:
    required = [
        "case_id",
        "source_path",
        "source_format",
        "source_sha256",
        "file_size_bytes",
        "broker",
        "account_alias",
        "parser_profile",
        "parser_version",
        "date_from",
        "date_to",
        "physical_row_count",
        "valid_trade_count",
        "excluded_row_count",
        "duplicate_row_count",
        "symbol_count",
        "contains_2236",
        "source_role",
        "validation_status",
        "known_limitations",
    ]
    m: dict[str, Any] = {"case_id": case_id, **fields}
    for key in required:
        if key not in m:
            m[key] = "UNKNOWN"
    # never invent True/0 for unknown booleans/counts — caller must set explicitly
    return m


def index_baseline_b() -> dict[str, Any]:
    output = ROOT / "output"
    entries: list[dict[str, Any]] = []
    if output.is_dir():
        for p in sorted(output.rglob("*")):
            if not p.is_file():
                continue
            name = p.name.lower()
            rel = str(p.relative_to(ROOT)).replace("\\", "/")
            tags: list[str] = []
            if "draft" in name:
                tags.append("DRAFT")
            if "2236" in name or "2236" in rel:
                tags.append("2236")
            if "hist" in name or "hist-01" in rel.lower():
                tags.append("HIST-01_candidate")
            if "bug" in name or "bug-01" in rel.lower():
                tags.append("BUG-01_candidate")
            if "合成" in p.name or "synthetic" in name:
                tags.append("synthetic")
            if "uat" in rel.lower():
                tags.append("uat_output")
            if not tags and p.suffix.lower() not in {".xlsx", ".xls", ".csv", ".json", ".md", ".txt"}:
                continue
            if not tags and p.suffix.lower() in {".xlsx", ".xls", ".csv", ".json"}:
                tags.append("report_or_artifact")
            try:
                sha = sha256_file(p)
                size = p.stat().st_size
            except OSError:
                sha = "UNKNOWN"
                size = None
            entries.append(
                {
                    "path": rel,
                    "sha256": sha,
                    "file_size_bytes": size,
                    "tags": tags,
                    "is_layer_c_answer": False,
                    "note": "baseline_b only；不得作為獨立 C 財務答案",
                }
            )

    known_deviations = [
        {
            "id": "HIST-01",
            "description": "舊版報表／歷史 DRAFT 已知偏差索引候選；細節待 Owner 對照",
            "is_layer_c": False,
        },
        {
            "id": "BUG-01",
            "description": "已知 bug 相關輸出／DRAFT；不得當正向財務依據",
            "is_layer_c": False,
        },
        {
            "id": "SYNTHETIC_2236",
            "description": "合成 2236 案例僅供結構／流程；非真實黃金 C",
            "is_layer_c": False,
        },
    ]
    return {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "role": "baseline_b",
        "disclaimer": (
            "本索引僅標示舊報表路徑與已知偏差；"
            "不得作為 Phase 2 獨立 C 標準答案；"
            "停止以平均拆分總額、人工虛假多列、舊版錯誤 DRAFT 作為財務正向依據。"
        ),
        "known_deviations": known_deviations,
        "entries": entries,
        "entry_count": len(entries),
    }


def main() -> None:
    for d in (MANIFEST_DIR, SOURCE_A, BASELINE_B, EXPECTED_C, RUNS_D, MUTATIONS, EVIDENCE):
        d.mkdir(parents=True, exist_ok=True)

    # placeholder for expected_c
    (EXPECTED_C / "README.md").write_text(
        "# expected_c\n\n本輪未驗收。Phase 2 授權前不得宣告已有獨立 C。\n",
        encoding="utf-8",
    )
    (RUNS_D / "README.md").write_text(
        "# runs_d\n\n後續新版輸出目錄；本輪空白。\n",
        encoding="utf-8",
    )
    (MUTATIONS / "README.md").write_text(
        "# mutations\n\n後續故障注入母本；本輪空白。\n"
        "INV-05：正確反例為 cost+1 且 income+1，或 cost-1 且 income-1（同向，profit 不變）。\n"
        "錯誤公式 cost±1 且 income∓1 已廢止。\n",
        encoding="utf-8",
    )

    # INV-01 before
    fp_before = fingerprint_bundle("phase0_before")
    write_json(EVIDENCE / "inv01_fingerprints_before.json", fp_before)

    # INV-02 analyses
    csv_keys = ["csv_2023", "csv_2024", "csv_2025", "csv_2026"]
    csv_analyses: dict[str, dict[str, Any]] = {}
    for key in csv_keys:
        csv_analyses[key] = analyze_capital_csv(SOURCES[key])
        write_json(
            EVIDENCE / f"inv02_{key}_counts.json",
            strip_rows_for_public(csv_analyses[key]),
        )

    capital_xls = analyze_html_xls(SOURCES["capital_xls"])
    write_json(EVIDENCE / "inv02_capital_xls_counts.json", capital_xls)

    esun = analyze_esun_xlsx(SOURCES["esun_xlsx"])
    write_json(EVIDENCE / "inv02_esun_xlsx_counts.json", esun)

    con = open_db_ro()
    try:
        db_inv = db_inventory(con)
        write_json(EVIDENCE / "inv02_db_inventory.json", db_inv)

        # INV-03 GOLD-001 (2024 csv, full + 2236)
        cc_2024 = cross_check_csv_to_db(
            csv_analyses["csv_2024"],
            con,
            file_sha256=fp_before["files"]["csv_2024"]["sha256"],
        )
        write_json(EVIDENCE / "inv03_gold001_csv2024_crosscheck.json", cc_2024)

        cc_2236 = cross_check_csv_to_db(
            csv_analyses["csv_2024"],
            con,
            file_sha256=fp_before["files"]["csv_2024"]["sha256"],
            symbol_filter="2236",
        )
        write_json(EVIDENCE / "inv03_gold001_2236_crosscheck.json", cc_2236)

        # 2236 mapping table (local evidence; may contain trade ids — not for PR body)
        map_2236 = {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "source": "csv_2024 A layer + trading.db read-only",
            "disclaimer": "本機 evidence；PR 公開回覆不得貼完整真實交易明細",
            "csv_rows": [
                r
                for r in csv_analyses["csv_2024"]["rows"]
                if r["symbol"] == "2236"
            ],
            "crosscheck_status": cc_2236["status"],
            "matched": [
                {
                    "csv_physical_line": m["csv_physical_line"],
                    "db_row_index": m["db_row_index"],
                    "trade_id": m["trade_id"],
                    "raw_row_id": m["raw_row_id"],
                    "match_ok": m["match_ok"],
                    "symbol": m["fields"]["symbol"]["db"],
                    "trade_date": m["fields"]["trade_date"]["db"],
                    "side": m["fields"]["side"]["db"],
                    "quantity": m["fields"]["quantity"]["db"],
                }
                for m in cc_2236.get("matches", [])
            ],
            "unmatched_csv": cc_2236.get("unmatched_csv", []),
            "unmatched_db": cc_2236.get("unmatched_db", []),
        }
        write_json(EVIDENCE / "phase1_2236_csv_db_map.json", map_2236)

        # GOLD-004: all four CSVs
        gold004: dict[str, Any] = {"cases": {}, "summary": {}}
        for key in csv_keys:
            cc = cross_check_csv_to_db(
                csv_analyses[key],
                con,
                file_sha256=fp_before["files"][key]["sha256"],
            )
            # store summary without full match detail in summary file; detail separate
            write_json(EVIDENCE / f"inv03_gold004_{key}_crosscheck.json", cc)
            gold004["cases"][key] = {
                "status": cc["status"],
                "csv_valid_trade_count": cc.get("csv_valid_trade_count"),
                "db_trade_count": cc.get("db_trade_count"),
                "matched_count": cc.get("matched_count"),
                "unmatched_csv_count": cc.get("unmatched_csv_count"),
                "unmatched_db_count": cc.get("unmatched_db_count"),
                "field_mismatch_count": cc.get("field_mismatch_count"),
                "batch_id": cc.get("batch_id"),
                "batch_filename": cc.get("batch_filename"),
            }
        gold004["summary"] = {
            "all_pass": all(c["status"] == "PASS" for c in gold004["cases"].values()),
            "csv_valid_sum": sum(
                csv_analyses[k]["valid_trade_count"] for k in csv_keys
            ),
            "db_trade_total": db_inv["trade_total"],
            "note": (
                "不得把 DB trade_total 當四份 CSV 實體列總和；"
                "應以各 batch.file_sha256 對應 valid_trade_count。"
            ),
        }
        write_json(EVIDENCE / "inv03_gold004_summary.json", gold004)
    finally:
        con.close()

    # INV-04 note
    inv04 = {
        "id": "INV-04",
        "title": "verify_detail_xlsx_finance 僅可重用骨架",
        "status": "DOCUMENTED",
        "statements": [
            "可重用 scripts/uat_fifo_same_day_2236.py::verify_detail_xlsx_finance 之讀取／比對骨架。",
            "不得認定其目前結果為可信財務標準答案（CR-10A 仍未結案）。",
            "不得用受測程式（FIFO／Projector／新版 Excel 輸出）反推 expected C。",
            "Phase 2 獨立 C 僅能由 A 原始欄位 + SPEC 以 Decimal 推導（本輪不實作）。",
        ],
        "references": [
            "scripts/uat_fifo_same_day_2236.py",
            "tests/test_uat_fifo_same_day_verdict.py",
            "docs/test/UAT_fifo_same_day_2236.md",
        ],
    }
    write_json(EVIDENCE / "inv04_verifier_skeleton_only.json", inv04)

    # INV-05 fault formula
    inv05 = {
        "id": "INV-05",
        "title": "故障注入反例公式修正",
        "status": "CORRECTED",
        "wrong_formula": "cost±1 且 income∓1（反向）— 會改變 profit，不是「profit 不變」反例",
        "correct_formula": [
            "cost+1 且 income+1（同向）→ profit 不變",
            "cost-1 且 income-1（同向）→ profit 不變",
        ],
        "purpose": "驗證驗證器是否獨立核對 cost／income，而非只靠 income-cost==profit",
        "tests_already_aligned": [
            "test_verify_detail_xlsx_finance_fails_when_cost_income_both_up",
            "test_verify_detail_xlsx_finance_fails_when_cost_income_both_down",
        ],
        "note": "後續 mutations／測試設計以此為準；本輪不實作 Phase 2+ mutations 母本。",
    }
    write_json(EVIDENCE / "inv05_fault_injection_formula.json", inv05)
    (MUTATIONS / "INV05_FORMULA.md").write_text(
        "# INV-05 故障注入公式\n\n"
        "## 正確（profit 不變）\n\n"
        "- `cost+1` 且 `income+1`\n"
        "- `cost-1` 且 `income-1`\n\n"
        "## 已廢止\n\n"
        "- `cost±1` 且 `income∓1`（反向會改變 profit）\n",
        encoding="utf-8",
    )

    # INV-01 after
    fp_after = fingerprint_bundle("phase0_after")
    write_json(EVIDENCE / "inv01_fingerprints_after.json", fp_after)

    drift: dict[str, Any] = {"status": "PASS", "drifts": []}
    for key in SOURCES:
        b = fp_before["files"].get(key, {})
        a = fp_after["files"].get(key, {})
        if b.get("sha256") != a.get("sha256") or b.get("file_size_bytes") != a.get(
            "file_size_bytes"
        ):
            drift["drifts"].append({"key": key, "before": b, "after": a})
    if drift["drifts"]:
        drift["status"] = "BLOCKER"
    write_json(EVIDENCE / "inv01_fingerprint_drift.json", drift)

    # gitignore confirmation
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    gitignore_check = {
        "data_ignored": "data/" in gi,
        "input_ignored": "input/" in gi,
        "output_ignored": "output/" in gi,
        "xls_ignored": "*.xls" in gi,
        "xlsx_ignored": "*.xlsx" in gi,
        "db_ignored": "*.db" in gi,
        "conclusion": (
            "data/ 整目錄已 ignore（含 data/golden/）；"
            "真實交易 golden 內容不應進入公開 Git。"
            if "data/" in gi
            else "BLOCKER: data/ 未在 gitignore"
        ),
        "status": "PASS" if "data/" in gi else "FAIL",
    }
    write_json(EVIDENCE / "phase1_gitignore_check.json", gitignore_check)

    # source_a index
    source_a_index = {
        "role": "A",
        "note": "僅索引；不改動原始 input／source_archive",
        "sources": {
            k: {
                "path": fp_after["files"][k]["path"],
                "sha256": fp_after["files"][k]["sha256"],
                "file_size_bytes": fp_after["files"][k]["file_size_bytes"],
            }
            for k in SOURCES
            if fp_after["files"][k].get("exists")
        },
    }
    write_json(SOURCE_A / "index.json", source_a_index)

    # baseline_b
    baseline = index_baseline_b()
    write_json(BASELINE_B / "index.json", baseline)

    # Manifests
    def sha_of(key: str) -> str:
        return fp_after["files"][key]["sha256"]

    def size_of(key: str) -> int:
        return fp_after["files"][key]["file_size_bytes"]

    # account alias from DB without exposing real label digits if possible
    account_alias = "capital_primary"
    if db_inv["brokers_accounts"]:
        # de-identify: broker name + generic
        bn = db_inv["brokers_accounts"][0].get("broker_name", "UNKNOWN")
        account_alias = f"{bn}_acct_A"

    m001 = build_manifest(
        "GOLD-001",
        source_path=fp_after["files"]["csv_2024"]["path"],
        source_format="capital_csv",
        source_sha256=sha_of("csv_2024"),
        file_size_bytes=size_of("csv_2024"),
        broker="群益",
        account_alias=account_alias,
        parser_profile="statement_html_v1",
        parser_version=1,
        date_from=csv_analyses["csv_2024"]["date_from"],
        date_to=csv_analyses["csv_2024"]["date_to"],
        physical_row_count=csv_analyses["csv_2024"]["physical_row_count"],
        header_row_count=csv_analyses["csv_2024"]["header_row_count"],
        valid_trade_count=csv_analyses["csv_2024"]["valid_trade_count"],
        excluded_row_count=csv_analyses["csv_2024"]["excluded_row_count"],
        duplicate_row_count=csv_analyses["csv_2024"]["duplicate_row_count"],
        symbol_count=csv_analyses["csv_2024"]["symbol_count"],
        contains_2236=csv_analyses["csv_2024"]["contains_2236"],
        per_symbol=csv_analyses["csv_2024"]["per_symbol"],
        source_role="A",
        validation_status="INVENTORIED_PHASE1",
        crosscheck_status=cc_2024["status"],
        crosscheck_2236_status=cc_2236["status"],
        known_limitations=[
            "CSV 為 A 層來源；不得以 DB 正規化列取代 A",
            "raw_row_id／trade_id／batch 僅存在於 DB（標 NOT_IN_SOURCE）",
            "獨立 C 財務預期尚未建立（Phase 2 未授權）",
        ],
        db_batch_id=cc_2024.get("batch_id"),
        evidence_paths=[
            "data/golden/evidence/inv03_gold001_csv2024_crosscheck.json",
            "data/golden/evidence/inv03_gold001_2236_crosscheck.json",
            "data/golden/evidence/phase1_2236_csv_db_map.json",
        ],
    )
    write_json(MANIFEST_DIR / "GOLD-001.json", m001)

    m002 = build_manifest(
        "GOLD-002",
        source_path=fp_after["files"]["capital_xls"]["path"],
        source_format="html_table_xls",
        source_sha256=sha_of("capital_xls"),
        file_size_bytes=size_of("capital_xls"),
        broker="群益",
        account_alias=account_alias,
        parser_profile=capital_xls["parser_profile"],
        parser_version=capital_xls["parser_version"],
        date_from=capital_xls["date_from"],
        date_to=capital_xls["date_to"],
        physical_row_count=capital_xls["physical_row_count"],
        physical_row_count_note=capital_xls["physical_row_count_note"],
        valid_trade_count=capital_xls["valid_trade_count"],
        excluded_row_count=capital_xls["excluded_row_count"],
        duplicate_row_count=capital_xls["duplicate_row_count"],
        symbol_count=capital_xls["symbol_count"],
        contains_2236=capital_xls["contains_2236"],
        per_symbol=capital_xls["per_symbol"],
        source_role="A",
        validation_status="INVENTORIED_PHASE1",
        known_limitations=[
            "預期 65／7 舊約數作廢；以本 Manifest 精確計數為準",
            "physical_row_count 採 HTML <tr> 數，非純文字列",
            "獨立 C 未建立",
        ],
    )
    write_json(MANIFEST_DIR / "GOLD-002.json", m002)

    # Esun account alias
    esun_alias = "esun_acct_A"
    for ba in db_inv["brokers_accounts"]:
        if "玉山" in str(ba.get("broker_name", "")):
            esun_alias = "玉山_acct_A"
            break

    m003 = build_manifest(
        "GOLD-003",
        source_path=fp_after["files"]["esun_xlsx"]["path"],
        source_format="esun_xlsx",
        source_sha256=sha_of("esun_xlsx"),
        file_size_bytes=size_of("esun_xlsx"),
        broker="玉山",
        account_alias=esun_alias,
        parser_profile=esun["parser_profile"],
        parser_version=esun["parser_version"],
        date_from=esun["date_from"],
        date_to=esun["date_to"],
        physical_row_count=esun["physical_row_count"],
        header_row_count=esun["header_row_count"],
        valid_trade_count=esun["valid_trade_count"],
        excluded_row_count=esun["excluded_row_count"],
        duplicate_row_count=esun["duplicate_row_count"],
        symbol_count=esun["symbol_count"],
        contains_2236=esun["contains_2236"],
        per_symbol=esun["per_symbol"],
        source_role="A",
        validation_status="INVENTORIED_PHASE1",
        known_limitations=esun.get("known_limitations", [])
        + [
            "預期 65／8 舊約數作廢；以本 Manifest 精確計數為準（valid=65／symbol=8 已重核）",
            "2236 僅現股賣出 2 筆、缺買進；不與群益混配；不自造期初",
            "獨立 C 未建立",
        ],
        symbol_2236_side_note="SELL_ONLY_2_ROWS_NO_BUY",
    )
    write_json(MANIFEST_DIR / "GOLD-003.json", m003)

    m004_sources = []
    for key, year in [
        ("csv_2023", "2023"),
        ("csv_2024", "2024"),
        ("csv_2025", "2025"),
        ("csv_2026", "2026"),
    ]:
        m004_sources.append(
            {
                "year": year,
                "source_path": fp_after["files"][key]["path"],
                "source_sha256": sha_of(key),
                "file_size_bytes": size_of(key),
                "physical_row_count": csv_analyses[key]["physical_row_count"],
                "header_row_count": csv_analyses[key]["header_row_count"],
                "valid_trade_count": csv_analyses[key]["valid_trade_count"],
                "excluded_row_count": csv_analyses[key]["excluded_row_count"],
                "duplicate_row_count": csv_analyses[key]["duplicate_row_count"],
                "symbol_count": csv_analyses[key]["symbol_count"],
                "contains_2236": csv_analyses[key]["contains_2236"],
                "date_from": csv_analyses[key]["date_from"],
                "date_to": csv_analyses[key]["date_to"],
                "crosscheck": gold004["cases"][key],
            }
        )

    m004 = build_manifest(
        "GOLD-004",
        source_path="MULTIPLE(see sources[])",
        source_format="capital_csv_multi_year",
        source_sha256="MULTIPLE(see sources[].source_sha256)",
        file_size_bytes="MULTIPLE(see sources[].file_size_bytes)",
        broker="群益",
        account_alias=account_alias,
        parser_profile="statement_html_v1",
        parser_version=1,
        date_from=format_manifest_date(
            date_bounds(
                [s["date_from"] for s in m004_sources if s["date_from"] != "UNKNOWN"]
            )[0]
        ),
        date_to=format_manifest_date(
            date_bounds(
                [s["date_to"] for s in m004_sources if s["date_to"] != "UNKNOWN"]
            )[1]
        ),
        physical_row_count=sum(s["physical_row_count"] for s in m004_sources),
        valid_trade_count=sum(s["valid_trade_count"] for s in m004_sources),
        excluded_row_count=sum(s["excluded_row_count"] for s in m004_sources),
        duplicate_row_count=sum(s["duplicate_row_count"] for s in m004_sources),
        symbol_count="SEE_PER_YEAR",
        contains_2236=any(s["contains_2236"] for s in m004_sources),
        source_role="A",
        validation_status="INVENTORIED_PHASE1",
        sources=m004_sources,
        db_trade_total=db_inv["trade_total"],
        db_mapping_note=(
            f"CSV valid 合計={sum(s['valid_trade_count'] for s in m004_sources)}；"
            f"DB trades 總計={db_inv['trade_total']}；"
            "不得把 DB 總筆數當 CSV 實體列總和；應對各 file_sha256 batch。"
        ),
        crosscheck_all_pass=gold004["summary"]["all_pass"],
        known_limitations=[
            "多檔來源；單一 source_sha256 不適用 → 見 sources[]",
            "獨立 C 未建立",
            "DB 可能含非四 CSV 之其他 batch（若 trade_total 不等於四檔 valid 合計須標明）",
        ],
        evidence_paths=[
            "data/golden/evidence/inv03_gold004_summary.json",
            "data/golden/evidence/inv02_db_inventory.json",
        ],
    )
    write_json(MANIFEST_DIR / "GOLD-004.json", m004)

    # Phase summary (public-safe)
    summary = {
        "phase": "0+1",
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "authorization": "Phase 0+1 only；Phase 2+ 未授權；CR-10A 仍未結案",
        "fingerprint_drift": drift["status"],
        "gitignore": gitignore_check["status"],
        "inv": {
            "INV-01": drift["status"],
            "INV-02": "DONE",
            "INV-03_GOLD001": cc_2024["status"],
            "INV-03_GOLD001_2236": cc_2236["status"],
            "INV-03_GOLD004": "PASS" if gold004["summary"]["all_pass"] else "FAIL",
            "INV-04": "DOCUMENTED",
            "INV-05": "CORRECTED",
        },
        "counts_public": {
            "GOLD-001_csv2024": {
                "physical_row_count": csv_analyses["csv_2024"]["physical_row_count"],
                "header_row_count": csv_analyses["csv_2024"]["header_row_count"],
                "valid_trade_count": csv_analyses["csv_2024"]["valid_trade_count"],
                "excluded_row_count": csv_analyses["csv_2024"]["excluded_row_count"],
                "duplicate_row_count": csv_analyses["csv_2024"]["duplicate_row_count"],
                "symbol_count": csv_analyses["csv_2024"]["symbol_count"],
                "contains_2236": csv_analyses["csv_2024"]["contains_2236"],
                "per_symbol_2236": csv_analyses["csv_2024"]["per_symbol"].get("2236"),
            },
            "GOLD-002_capital_xls": {
                "physical_row_count": capital_xls["physical_row_count"],
                "valid_trade_count": capital_xls["valid_trade_count"],
                "excluded_row_count": capital_xls["excluded_row_count"],
                "duplicate_row_count": capital_xls["duplicate_row_count"],
                "symbol_count": capital_xls["symbol_count"],
                "contains_2236": capital_xls["contains_2236"],
            },
            "GOLD-003_esun_xlsx": {
                "physical_row_count": esun["physical_row_count"],
                "valid_trade_count": esun["valid_trade_count"],
                "excluded_row_count": esun["excluded_row_count"],
                "duplicate_row_count": esun["duplicate_row_count"],
                "symbol_count": esun["symbol_count"],
                "contains_2236": esun["contains_2236"],
            },
            "GOLD-004": {
                "csv_valid_sum": gold004["summary"]["csv_valid_sum"],
                "db_trade_total": gold004["summary"]["db_trade_total"],
                "per_year_valid": {
                    k: csv_analyses[k]["valid_trade_count"] for k in csv_keys
                },
                "per_year_physical": {
                    k: csv_analyses[k]["physical_row_count"] for k in csv_keys
                },
            },
        },
        "sha256_full": {
            k: fp_after["files"][k]["sha256"]
            for k in SOURCES
            if fp_after["files"][k].get("exists")
        },
        "sha256_vs_plan": {
            k: fp_after["files"][k].get("matches_plan_expected")
            for k in EXPECTED_SHA256
        },
        "artifacts": {
            "manifest": "data/golden/manifest/",
            "evidence": "data/golden/evidence/",
            "source_a": "data/golden/source_a/index.json",
            "baseline_b": "data/golden/baseline_b/index.json",
            "expected_c": "data/golden/expected_c/ (empty pending Phase 2)",
        },
        "blockers": [],
        "open_items": [
            "Phase 2 獨立 C 未授權",
            "CR-10A 仍未結案",
            "不 Commit／Push／Merge",
        ],
    }
    if drift["status"] != "PASS":
        summary["blockers"].append("INV-01 fingerprint drift")
    if cc_2024["status"] != "PASS":
        summary["blockers"].append("INV-03 GOLD-001 crosscheck FAIL")
    if cc_2236["status"] != "PASS":
        summary["blockers"].append("INV-03 GOLD-001 2236 crosscheck FAIL")
    if not gold004["summary"]["all_pass"]:
        summary["blockers"].append("INV-03 GOLD-004 crosscheck FAIL")
    if gitignore_check["status"] != "PASS":
        summary["blockers"].append("gitignore data/ missing")

    # GOLD-CR-08：鎖定 SHA256 不一致 → blocker（非僅 open_items）
    actual_sha = {
        k: fp_after["files"][k]["sha256"]
        for k in EXPECTED_SHA256
        if fp_after["files"].get(k, {}).get("exists")
    }
    lock_bad = sha256_lock_mismatches(EXPECTED_SHA256, actual_sha)
    summary["sha256_lock_mismatches"] = lock_bad
    if lock_bad:
        summary["blockers"].append(f"GOLD-CR-08 sha256_lock_mismatch:{','.join(lock_bad)}")

    inv_fail = any(
        summary["inv"][k] not in {"PASS", "DONE", "DOCUMENTED", "CORRECTED"}
        for k in summary["inv"]
    )
    code = inventory_exit_code(blockers=summary["blockers"], inv_fail=inv_fail)
    summary["exit_code"] = code

    write_json(EVIDENCE / "phase01_summary.json", summary)

    readme = f"""# Golden Phase 0+1 Evidence

- 完成時間（UTC）：{summary['completed_at_utc']}
- 授權：僅 Phase 0+1；**CR-10A 仍未結案**；不進入 Phase 2
- 指紋漂移：{drift['status']}
- GOLD-001 交叉：{cc_2024['status']}；2236：{cc_2236['status']}
- GOLD-004 交叉：{'PASS' if gold004['summary']['all_pass'] else 'FAIL'}
- gitignore：{gitignore_check['status']}
- exit_code：{code}

詳見 `phase01_summary.json`。真實交易明細僅存本機 evidence，勿貼 PR。
"""
    (EVIDENCE / "README.md").write_text(readme, encoding="utf-8")
    (GOLDEN / "README.md").write_text(
        "# data/golden\n\n"
        "A/B/C/D 四層驗收布局。本輪僅填 manifest／source_a／baseline_b／evidence。\n"
        "`expected_c` 未驗收。禁止提交真實交易內容至公開 Git。\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
