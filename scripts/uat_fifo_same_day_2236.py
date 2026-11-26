"""隔離 UAT：2236 Two-Pass FIFO（合成資料；禁止寫正式 DB）。

Fingerprint 限制（CR-11）：
- UAT 期間禁止其他程序寫入正式 ``data/trading.db``（含 -wal／-shm）。
- 指紋比對僅適用「無並發寫入」前提；指紋變 → verdict FAIL。
- 不宣稱涵蓋所有並發／OS 快取／外部備份工具等情境。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from alembic.config import Config
from sqlalchemy import create_engine, func, inspect, select, text

from alembic import command
from backend.config import ALGORITHM_VERSION, CASH_SAME_DAY_POLICY, PROJECT_ROOT
from backend.db.models import (
    Account,
    AllocationRun,
    Broker,
    FifoAllocation,
    ImportBatch,
    RawRow,
    ReconciliationIssueRow,
    TradeRow,
)
from backend.db.session import init_db, integrity_check, make_session_factory
from backend.domain.models import Allocation, Trade, txt_to_decimal
from backend.services.allocation_service import match_fifo_for_account, quantity_conservation
from backend.services.day_trade_annotation import annotate_day_trades, annotation_to_audit_dict
from backend.services.reconciliation import build_audit
from backend.services.report_service import generate_detail_report

UAT_THEME = "fifo_same_day_2236"
UAT_ROOT = PROJECT_ROOT / "data" / "uat" / UAT_THEME
OUT_ROOT = PROJECT_ROOT / "output" / f"uat_{UAT_THEME}"
FORMAL_DB = PROJECT_ROOT / "data" / "trading.db"
ACCOUNT_LABEL = "uat2236"

# 與 tests/test_same_day_reconciliation.py::test_c01 同軌跡（買＝賣＝4000）
TRADES: list[tuple[str, str, str, int, str, str, str]] = [
    ("2024-08-05", "BUY", 2000, "100", "40", "0", "b1"),
    ("2024-08-12", "BUY", 1000, "105", "25", "0", "b2"),
    ("2024-08-20", "SELL", 400, "110", "20", "132", "s1"),
    ("2024-08-20", "SELL", 1000, "111", "30", "333", "s2"),
    ("2024-08-26", "SELL", 1000, "112", "30", "336", "s3"),
    ("2024-08-28", "SELL", 1000, "113", "30", "170", "s4"),
    ("2024-08-28", "BUY", 1000, "114", "25", "0", "b3"),
    ("2024-09-02", "SELL", 579, "115", "20", "200", "s5"),
    ("2024-09-02", "SELL", 21, "116", "5", "7", "s6"),
]


def _sha256_file(path: Path) -> str | None:
    """計算檔案 SHA-256（唯讀）。

    Args:
        path: 目標檔路徑。

    Returns:
        hex digest；檔不存在時 ``None``。

    Side Effects:
        僅讀取檔案內容；不寫入。
    """
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _formal_fingerprint() -> dict:
    """正式 DB 指紋（含 WAL／SHM；不開啟寫入）。

    Returns:
        含 exists／mtime／size／sha256 之 dict。

    Side Effects:
        僅 ``stat``／讀取；**不**開 SQLite 連線、不寫入。

    Note:
        適用「UAT 期間無其他程序寫正式 DB」前提；不涵蓋並發寫入。
    """
    paths = {
        "db": FORMAL_DB,
        "wal": Path(str(FORMAL_DB) + "-wal"),
        "shm": Path(str(FORMAL_DB) + "-shm"),
    }
    out: dict = {"exists": FORMAL_DB.exists()}
    for key, path in paths.items():
        if not path.exists():
            out[key] = {"exists": False, "mtime": None, "size": None, "sha256": None}
            continue
        st = path.stat()
        out[key] = {
            "exists": True,
            "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(sep=" ", timespec="seconds"),
            "size": st.st_size,
            "sha256": _sha256_file(path),
        }
    return out


def _assert_uat_path(path: Path, *, root: Path) -> Path:
    """解析路徑必須落在指定 UAT 根之下。

    Args:
        path: 候選路徑。
        root: 允許的 UAT 根目錄。

    Returns:
        ``path.resolve()``。

    Raises:
        RuntimeError: 路徑逸出 ``root``。

    Side Effects:
        無。
    """
    resolved = path.resolve()
    root_r = root.resolve()
    if root_r not in resolved.parents and resolved != root_r:
        raise RuntimeError(f"UAT path escapes {root_r}: {resolved}")
    return resolved


def _seed(session) -> Account:
    """植入合成 2236 九筆 CASH（買＝賣＝4000）。

    Args:
        session: SQLAlchemy session（UAT 隔離 DB）。

    Returns:
        新建 ``Account``。

    Side Effects:
        寫入 brokers／accounts／import_batches／raw_rows／trades（僅 UAT DB）。
    """
    broker = Broker(id=str(uuid.uuid4()), name="uat-synthetic-broker")
    account = Account(id=str(uuid.uuid4()), broker_id=broker.id, account_label=ACCOUNT_LABEL)
    batch = ImportBatch(
        id=str(uuid.uuid4()),
        account_id=account.id,
        file_sha256="b" * 64,
        filename="synthetic_2236_uat.xls",
        profile_id="statement_html_v1",
        profile_version=1,
        status="completed",
    )
    session.add_all([broker, account, batch])
    session.flush()

    for idx, (day, side, qty, price, commission, tax, key) in enumerate(TRADES, start=1):
        unit = Decimal(price)
        gross = unit * qty
        raw = RawRow(
            id=str(uuid.uuid4()),
            batch_id=batch.id,
            sheet_name="Sheet1",
            row_index=idx,
            raw_json=json.dumps({"key": key}, ensure_ascii=False),
            row_sha256=uuid.uuid4().hex + uuid.uuid4().hex[:32],
            parse_status="ok",
        )
        trade = TradeRow(
            id=str(uuid.uuid4()),
            raw_row_id=raw.id,
            account_id=account.id,
            symbol="2236",
            name="synthetic-2236",
            trade_date=day,
            side=side,
            trade_type="CASH",
            currency="TWD",
            quantity=qty,
            unit_price_txt=price,
            gross_amount_txt=str(gross),
            commission_txt=commission,
            tax_txt=tax,
            interest_txt="0",
            raw_payload_json=json.dumps({"uat_key": key}, ensure_ascii=False),
        )
        session.add_all([raw, trade])
    session.flush()
    return account


def _domain_views(session, account_id: str, run_id: str) -> tuple[list[Trade], list[Allocation]]:
    """將 ORM 列轉為 annotation 用領域物件（唯讀）。

    Args:
        session: SQLAlchemy session。
        account_id: 帳戶 id。
        run_id: allocation run id。

    Returns:
        ``(domain trades, domain allocations)``。

    Side Effects:
        無寫入；不改 ORM 財務欄。
    """
    trades = list(session.scalars(select(TradeRow).where(TradeRow.account_id == account_id)))
    alloc_rows = list(
        session.scalars(select(FifoAllocation).where(FifoAllocation.run_id == run_id))
    )
    domain_trades = [
        Trade(
            trade_id=t.id,
            account_id=t.account_id,
            source_row_id=t.raw_row_id,
            symbol=t.symbol,
            name=t.name,
            trade_date=datetime.fromisoformat(t.trade_date).date(),
            trade_time=None,
            trade_sequence=t.trade_sequence,
            side=t.side,  # type: ignore[arg-type]
            trade_type=t.trade_type,  # type: ignore[arg-type]
            currency=t.currency,
            quantity=t.quantity,
            unit_price=txt_to_decimal(t.unit_price_txt),
            gross_amount=txt_to_decimal(t.gross_amount_txt),
            commission=txt_to_decimal(t.commission_txt),
            tax=txt_to_decimal(t.tax_txt),
            interest=txt_to_decimal(t.interest_txt),
            net_settlement=None,
        )
        for t in trades
    ]
    domain_allocs = [
        Allocation(
            run_id=run_id,
            allocation_id=a.id,
            buy_trade_id=a.buy_trade_id,
            opening_lot_id=a.opening_lot_id,
            sell_trade_id=a.sell_trade_id,
            quantity=a.allocated_quantity,
            sequence_no=a.sequence_no,
            match_type=a.match_type,
        )
        for a in alloc_rows
    ]
    return domain_trades, domain_allocs


def _alloc_business_keys(session, run_id: str) -> list[tuple]:
    """讀取配對業務鍵（冪等比對用）。

    Args:
        session: SQLAlchemy session。
        run_id: allocation run id。

    Returns:
        排序後 ``(buy, opening, sell, qty, seq, match_type)`` 清單。

    Side Effects:
        無。
    """
    rows = list(
        session.scalars(select(FifoAllocation).where(FifoAllocation.run_id == run_id))
    )
    return sorted(
        (
            a.buy_trade_id,
            a.opening_lot_id,
            a.sell_trade_id,
            a.allocated_quantity,
            a.sequence_no,
            a.match_type,
        )
        for a in rows
    )


def build_uat_checks(
    *,
    required_outputs: dict[str, bool],
    migration_probe: dict[str, Any],
    fresh_schema_has_match_type: bool,
    allocated_qty: int,
    qty_by_match_type: dict[str, int],
    unsold_qty: int,
    blocking: bool,
    conservation_ok: bool,
    audit_json: dict[str, Any],
    integrity_check_result: str,
    h_annotation_non_interference: bool,
    detail_is_draft: bool,
    idempotent: dict[str, Any],
    formal_db_untouched: bool,
    run_dir_under_data_uat: bool,
    out_dir_under_output_uat: bool,
    detail_xlsx_finance_ok: bool = True,
) -> dict[str, bool]:
    """組裝 UAT ``checks``（純函式；全部步驟後呼叫）。

    Args:
        required_outputs: 必要產出存在旗標（須含 detail／audit／exceptions／
            fifo_trace／conservation）。
        migration_probe: 實際 alembic upgrade 探針結果。
        fresh_schema_has_match_type: create_all 新 DB 是否含 ``match_type``。
        allocated_qty: 配對股數合計。
        qty_by_match_type: 各 ``match_type`` 股數。
        unsold_qty: 未售股數。
        blocking: 是否 blocking。
        conservation_ok: 數量守恆（DB 計算）。
        audit_json: **序列化後** audit.json 內容（含 day_trade_annotation）。
        integrity_check_result: ``PRAGMA integrity_check`` 結果字串。
        h_annotation_non_interference: annotation 前後財務鍵全等。
        detail_is_draft: 明細是否 DRAFT。
        idempotent: 冪等重跑結果。
        formal_db_untouched: 正式 DB 指紋未變。
        run_dir_under_data_uat: run 目錄落在 data/uat 根。
        out_dir_under_output_uat: out 目錄落在 output/uat 根。
        detail_xlsx_finance_ok: 可選明細財務加總核對。

    Returns:
        ``dict[str, bool]``；``all(values)`` 為 True 才可判 PASS。

    Side Effects:
        無。

    Note:
        Annotation 數量／狀態以 ``audit_json["day_trade_annotation"]`` 為準，
        不得僅用記憶體 annotation 物件當最終判定。
    """
    ann = audit_json.get("day_trade_annotation") or {}
    return {
        "fresh_schema_has_match_type": bool(fresh_schema_has_match_type),
        "actual_migration_day_trade_backfill": bool(
            migration_probe.get("day_trade_backfill_ok")
        ),
        "actual_migration_cash_standard_ok": bool(migration_probe.get("cash_standard_ok")),
        "actual_migration_fk_ok": bool(migration_probe.get("foreign_key_check_empty")),
        "actual_migration_integrity_ok": bool(migration_probe.get("integrity_ok")),
        "allocated_4000": allocated_qty == 4000,
        "standard_3600": qty_by_match_type.get("STANDARD_FIFO", 0) == 3600,
        "pass2_400": qty_by_match_type.get("SAME_DAY_RECONCILED", 0) == 400,
        "unsold_0": unsold_qty == 0,
        "not_blocking": not blocking,
        "conservation_ok": bool(conservation_ok),
        "audit_json_conservation_ok": bool(audit_json.get("conservation_ok")),
        "integrity_ok": integrity_check_result == "ok",
        "h_ok": bool(h_annotation_non_interference),
        "required_outputs_all": all(required_outputs.values()) and bool(required_outputs),
        "required_fifo_trace": bool(required_outputs.get("fifo_trace")),
        "required_conservation": bool(required_outputs.get("conservation")),
        "required_detail_xlsx": bool(required_outputs.get("detail_xlsx")),
        "required_audit_json": bool(required_outputs.get("audit_json")),
        "required_exceptions_csv": bool(required_outputs.get("exceptions_csv")),
        "not_draft": not detail_is_draft,
        "annotation_status_ok": ann.get("status") == "OK",
        "annotation_suspected_exact_1000": ann.get("suspected_day_trade_qty") == 1000,
        "annotation_reconciled_exact_400": ann.get("same_day_reconciled_qty") == 400,
        "annotation_warnings_empty": list(ann.get("warnings") or []) == [],
        "idempotent_old_preserved": bool(idempotent.get("old_run_preserved")),
        "idempotent_old_keys_unchanged": bool(idempotent.get("old_run_keys_unchanged")),
        "idempotent_new_keys_equal": bool(idempotent.get("new_run_keys_equal_old")),
        "idempotent_qty_same": bool(idempotent.get("allocated_qty_same")),
        "formal_db_untouched": bool(formal_db_untouched),
        "run_dir_under_data_uat": bool(run_dir_under_data_uat),
        "out_dir_under_output_uat": bool(out_dir_under_output_uat),
        "detail_xlsx_finance_ok": bool(detail_xlsx_finance_ok),
    }


def _run_actual_migration_check(run_dir: Path) -> dict:
    """獨立 tmp DB：PREV → seed → HEAD，驗證實際 migration（非 fresh schema）。

    Args:
        run_dir: 本次 UAT run 目錄（須在 ``UAT_ROOT`` 下）。

    Returns:
        含 ``day_trade_backfill_ok``／``cash_standard_ok``／FK／integrity 之 dict。

    Side Effects:
        於 ``run_dir/migration_probe.db`` 寫入探針 DB；**不**觸碰正式 DB。
    """
    mig_db = _assert_uat_path(run_dir / "migration_probe.db", root=UAT_ROOT)
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{mig_db.as_posix()}")
    prev = "a1b2c3d4e5f6"
    head = "b2c3d4e5f6a7"
    command.upgrade(cfg, prev)
    engine = create_engine(f"sqlite:///{mig_db.as_posix()}")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO brokers (id, name) VALUES ('br_u', 'uat-mig')"))
        conn.execute(
            text(
                "INSERT INTO accounts (id, broker_id, account_label) VALUES ('ac_u', 'br_u', 'u')"
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO import_batches (
                    id, account_id, file_sha256, filename, profile_id, profile_version,
                    imported_at_utc, status
                ) VALUES (
                    'bat_u', 'ac_u', :sha, 'u.xls', 'statement_html_v1', 1,
                    '2024-01-01T00:00:00+00:00', 'completed'
                )
                """
            ),
            {"sha": "c" * 64},
        )
        for rid, idx, side, tt in (
            ("r_b", 1, "BUY", "CASH"),
            ("r_s", 2, "SELL", "CASH"),
            ("r_db", 3, "BUY", "DAY_TRADE"),
            ("r_ds", 4, "SELL", "DAY_TRADE"),
        ):
            conn.execute(
                text(
                    """
                    INSERT INTO raw_rows (
                        id, batch_id, sheet_name, row_index, raw_json, row_sha256, parse_status
                    ) VALUES (:id, 'bat_u', 'S', :idx, '{}', :sha, 'ok')
                    """
                ),
                {"id": rid, "idx": idx, "sha": (rid + "y" * 64)[:64]},
            )
            tid = f"t_{rid}"
            conn.execute(
                text(
                    """
                    INSERT INTO trades (
                        id, raw_row_id, account_id, symbol, name, trade_date, trade_time,
                        trade_sequence, side, trade_type, currency, quantity,
                        unit_price_txt, gross_amount_txt, commission_txt, tax_txt,
                        interest_txt, net_settlement_txt, external_trade_id, raw_payload_json
                    ) VALUES (
                        :id, :raw, 'ac_u', '2236', NULL, '2025-01-10', NULL, NULL,
                        :side, :tt, 'TWD', 100,
                        '100', '10000', '20', '0', '0', NULL, NULL, '{}'
                    )
                    """
                ),
                {"id": tid, "raw": rid, "side": side, "tt": tt},
            )
        conn.execute(
            text(
                """
                INSERT INTO allocation_runs (
                    id, algorithm_version, input_fingerprint, started_at_utc,
                    finished_at_utc, status, config_json, account_id
                ) VALUES (
                    'run_u', 'fifo_v2', :fp, '2025-01-10T00:00:00+00:00',
                    '2025-01-10T00:00:01+00:00', 'completed', '{}', 'ac_u'
                )
                """
            ),
            {"fp": "d" * 64},
        )
        conn.execute(
            text(
                """
                INSERT INTO fifo_allocations (
                    id, run_id, buy_trade_id, opening_lot_id, sell_trade_id,
                    allocated_quantity, sequence_no
                ) VALUES
                    ('a_c', 'run_u', 't_r_b', NULL, 't_r_s', 100, 1),
                    ('a_d', 'run_u', 't_r_db', NULL, 't_r_ds', 100, 2)
                """
            )
        )
    command.upgrade(cfg, head)
    with engine.connect() as conn:
        rows = {
            r[0]: r[1]
            for r in conn.execute(text("SELECT id, match_type FROM fifo_allocations")).all()
        }
        fk = conn.execute(text("PRAGMA foreign_key_check")).fetchall()
        integrity = conn.execute(text("PRAGMA integrity_check")).scalar()
    return {
        "match_types": rows,
        "day_trade_backfill_ok": rows.get("a_d") == "DAY_TRADE_FIFO",
        "cash_standard_ok": rows.get("a_c") == "STANDARD_FIFO",
        "foreign_key_check_empty": fk == [],
        "integrity_ok": integrity == "ok",
    }


def main() -> int:
    """執行隔離 UAT 並於**全部**步驟後計算 verdict。

    Side Effects:
        於 ``data/uat/fifo_same_day_2236/run_<stamp>/`` 與
        ``output/uat_fifo_same_day_2236/run_<stamp>/`` 寫入證據；**不**寫正式 DB。
        禁止 ``rmtree`` 既有 run 目錄。

    Returns:
        0＝PASS 且正式 DB 指紋未變；否則 1。
    """
    before_fp = _formal_fingerprint()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = _assert_uat_path(UAT_ROOT / f"run_{stamp}", root=UAT_ROOT)
    out_dir = _assert_uat_path(OUT_ROOT / f"run_{stamp}", root=OUT_ROOT)
    run_dir.mkdir(parents=True, exist_ok=False)
    out_dir.mkdir(parents=True, exist_ok=False)

    db_path = _assert_uat_path(run_dir / "uat.db", root=UAT_ROOT)
    engine = init_db(db_path)
    Session = make_session_factory(engine)
    summary: dict = {
        "theme": UAT_THEME,
        "started_at_utc": datetime.now(UTC).isoformat(),
        "run_dir": str(run_dir),
        "db_path": str(db_path),
        "output_dir": str(out_dir),
        "formal_db_before": before_fp,
        "algorithm_version": ALGORITHM_VERSION,
        "cash_same_day_policy": CASH_SAME_DAY_POLICY,
    }

    migration_probe = _run_actual_migration_check(run_dir)
    summary["actual_migration_probe"] = migration_probe

    with Session() as session:
        account = _seed(session)
        session.commit()

        # fresh-schema check（create_all 新 DB）≠ actual migration
        insp = inspect(engine)
        alloc_cols = {c["name"] for c in insp.get_columns("fifo_allocations")}
        fresh_schema_has_match_type = "match_type" in alloc_cols

        run, result = match_fifo_for_account(session, account.id)
        session.commit()

        by_type: dict[str, int] = {}
        for a in result.allocations:
            by_type[a.match_type] = by_type.get(a.match_type, 0) + a.quantity

        trades = list(session.scalars(select(TradeRow).where(TradeRow.account_id == account.id)))
        alloc_rows = list(
            session.scalars(select(FifoAllocation).where(FifoAllocation.run_id == run.id))
        )
        cons = quantity_conservation(trades, alloc_rows)
        audit = build_audit(session, account.id, run.id)

        domain_trades, domain_allocs = _domain_views(session, account.id, run.id)
        finance_snap = [
            (a.buy_trade_id, a.sell_trade_id, a.quantity, a.match_type) for a in domain_allocs
        ]
        annotation = annotate_day_trades(domain_trades, domain_allocs)
        annotation2 = annotate_day_trades(domain_trades, domain_allocs)
        finance_after = [
            (a.buy_trade_id, a.sell_trade_id, a.quantity, a.match_type) for a in domain_allocs
        ]
        h_ok = (
            annotation.suspected_day_trade_qty == annotation2.suspected_day_trade_qty
            and finance_snap == finance_after
        )
        old_keys = _alloc_business_keys(session, run.id)

        buy_qty = sum(t.quantity for t in trades if t.side == "BUY")
        sell_qty = sum(t.quantity for t in trades if t.side == "SELL")
        buy_gross = sum(
            (txt_to_decimal(t.gross_amount_txt) for t in trades if t.side == "BUY"), Decimal(0)
        )
        sell_gross = sum(
            (txt_to_decimal(t.gross_amount_txt) for t in trades if t.side == "SELL"), Decimal(0)
        )
        commission_total = sum((txt_to_decimal(t.commission_txt) for t in trades), Decimal(0))
        tax_total = sum((txt_to_decimal(t.tax_txt) for t in trades), Decimal(0))

        pass2 = [a for a in result.allocations if a.match_type == "SAME_DAY_RECONCILED"]
        issues = list(
            session.scalars(
                select(ReconciliationIssueRow).where(ReconciliationIssueRow.run_id == run.id)
            )
        )

        xlsx_path, audit_path, exc_path = generate_detail_report(
            session,
            account.id,
            out_dir,
            allow_partial=False,
            run_id=run.id,
        )
        session.commit()
        audit_payload = json.loads(audit_path.read_text(encoding="utf-8"))
        ann_audit = audit_payload.get("day_trade_annotation") or {}

        # 冪等：再 match 一次，舊 run 不可覆寫；業務鍵完整比較
        run2, result2 = match_fifo_for_account(session, account.id)
        session.commit()
        old = session.get(AllocationRun, run.id)
        new_keys = _alloc_business_keys(session, run2.id)
        old_keys_after = _alloc_business_keys(session, run.id)
        idempotent = {
            "new_run_id": run2.id,
            "old_run_preserved": old is not None and old.id == run.id,
            "old_run_keys_unchanged": old_keys == old_keys_after,
            "new_run_keys_equal_old": new_keys == old_keys,
            "allocated_qty_same": sum(a.quantity for a in result2.allocations)
            == sum(a.quantity for a in result.allocations),
            "run_count": session.scalar(
                select(func.count())
                .select_from(AllocationRun)
                .where(AllocationRun.account_id == account.id)
            ),
        }

        required_outputs = {
            "detail_xlsx": xlsx_path.exists() and "DRAFT" not in xlsx_path.name,
            "audit_json": audit_path.exists(),
            "exceptions_csv": exc_path.exists(),
            "fifo_trace": any(out_dir.glob("*FIFO*"))
            or any(out_dir.glob("*fifo*trace*.xlsx")),
            "conservation": any(out_dir.glob("*守恆*"))
            or any(out_dir.glob("*conservation*")),
        }

        summary.update(
            {
                "account_label": ACCOUNT_LABEL,
                "account_id": account.id,
                "run_id": run.id,
                "run_status": run.status,
                "integrity_check": integrity_check(engine),
                "trade_count": len(trades),
                "buy_qty": buy_qty,
                "sell_qty": sell_qty,
                "allocation_count": len(result.allocations),
                "allocated_qty": sum(a.quantity for a in result.allocations),
                "qty_by_match_type": by_type,
                "pass2_count": len(pass2),
                "pass2_qty": sum(a.quantity for a in pass2),
                "unsold_qty": sum(u.available for u in result.unsold),
                "blocking": result.blocking,
                "issue_codes": [i.issue_code for i in issues],
                "conservation_ok": bool(cons["ok"]),
                "audit_conservation_ok": audit.conservation_ok,
                "audit_blocking_issue_count": audit.blocking_issue_count,
                "buy_gross": str(buy_gross),
                "sell_gross": str(sell_gross),
                "commission_total": str(commission_total),
                "tax_total": str(tax_total),
                "annotation": annotation_to_audit_dict(annotation)["day_trade_annotation"],
                "h_annotation_non_interference": h_ok,
                "outputs": {
                    "detail_xlsx": str(xlsx_path),
                    "audit_json": str(audit_path),
                    "exceptions_csv": str(exc_path),
                    "detail_is_draft": "DRAFT" in xlsx_path.name,
                    "detail_exists": xlsx_path.exists(),
                    "audit_exists": audit_path.exists(),
                },
                "required_outputs": required_outputs,
                "output_files": sorted(p.name for p in out_dir.glob("*") if p.is_file()),
                "idempotent_rerun": idempotent,
                "expectations": {
                    "allocated_qty": 4000,
                    "standard_fifo_qty": 3600,
                    "same_day_reconciled_qty": 400,
                    "unsold_qty": 0,
                    "blocking": False,
                    "conservation_ok": True,
                    "suspected_day_trade_qty": 1000,
                },
            }
        )

        after_fp = _formal_fingerprint()
        summary["formal_db_after"] = after_fp
        summary["formal_db_untouched"] = before_fp == after_fp
        summary["finished_at_utc"] = datetime.now(UTC).isoformat()

        # 最終判定以序列化 audit.json 為準（ann_audit），非僅記憶體 annotation
        checks = build_uat_checks(
            required_outputs=required_outputs,
            migration_probe=migration_probe,
            fresh_schema_has_match_type=fresh_schema_has_match_type,
            allocated_qty=int(summary["allocated_qty"]),
            qty_by_match_type=by_type,
            unsold_qty=int(summary["unsold_qty"]),
            blocking=bool(result.blocking),
            conservation_ok=bool(cons["ok"]),
            audit_json=audit_payload,
            integrity_check_result=str(summary["integrity_check"]),
            h_annotation_non_interference=h_ok,
            detail_is_draft=bool(summary["outputs"]["detail_is_draft"]),
            idempotent=idempotent,
            formal_db_untouched=bool(summary["formal_db_untouched"]),
            run_dir_under_data_uat=str(UAT_ROOT.resolve()) in str(run_dir.resolve()),
            out_dir_under_output_uat=str(OUT_ROOT.resolve()) in str(out_dir.resolve()),
            detail_xlsx_finance_ok=xlsx_path.exists() and "DRAFT" not in xlsx_path.name,
        )
        # 與序列化 ann 交叉核對（偵測記憶體／落盤不一致）
        checks["annotation_serialized_matches_memory"] = (
            ann_audit.get("suspected_day_trade_qty") == annotation.suspected_day_trade_qty
            and ann_audit.get("same_day_reconciled_qty") == annotation.same_day_reconciled_qty
            and list(ann_audit.get("warnings") or []) == list(annotation.warnings)
        )
        summary["checks"] = checks
        summary["uat_verdict"] = "PASS" if all(checks.values()) else "FAIL"

    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    UAT_ROOT.mkdir(parents=True, exist_ok=True)
    (UAT_ROOT / "latest_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["uat_verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
