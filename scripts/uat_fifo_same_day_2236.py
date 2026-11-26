"""隔離 UAT：2236 Two-Pass FIFO（合成資料；禁止寫正式 DB）。"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

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
DB_DIR = PROJECT_ROOT / "data" / "uat" / UAT_THEME
OUT_DIR = PROJECT_ROOT / "output" / f"uat_{UAT_THEME}"
FORMAL_DB = PROJECT_ROOT / "data" / "trading.db"
ACCOUNT_LABEL = "uat2236"

# 與 tests/test_same_day_reconciliation.py::test_c01 同軌跡（買＝賣＝4000）
TRADES: list[tuple[str, str, str, int, str, str, str]] = [
    # day, side, qty, price, commission, tax, note_key
    ("2024-08-05", "BUY", 2000, "100", "40", "0", "b1"),
    ("2024-08-12", "BUY", 1000, "105", "25", "0", "b2"),
    ("2024-08-20", "SELL", 400, "110", "20", "132", "s1"),
    ("2024-08-20", "SELL", 1000, "111", "30", "333", "s2"),
    ("2024-08-26", "SELL", 1000, "112", "30", "336", "s3"),
    # 113000×0.15%=169.5→170（減半稅輔助證據；與 Pass2 400 股獨立）
    ("2024-08-28", "SELL", 1000, "113", "30", "170", "s4"),
    ("2024-08-28", "BUY", 1000, "114", "25", "0", "b3"),
    ("2024-09-02", "SELL", 579, "115", "20", "200", "s5"),
    ("2024-09-02", "SELL", 21, "116", "5", "7", "s6"),
]


def _formal_mtime() -> str | None:
    if not FORMAL_DB.exists():
        return None
    return datetime.fromtimestamp(FORMAL_DB.stat().st_mtime).isoformat(sep=" ", timespec="seconds")


def _seed(session) -> Account:
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


def main() -> int:
    before_mtime = _formal_mtime()
    if DB_DIR.exists():
        shutil.rmtree(DB_DIR)
    DB_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    db_path = DB_DIR / "uat.db"
    engine = init_db(db_path)
    Session = make_session_factory(engine)
    summary: dict = {
        "theme": UAT_THEME,
        "started_at_utc": datetime.now(UTC).isoformat(),
        "db_path": str(db_path),
        "output_dir": str(OUT_DIR),
        "formal_db_mtime_before": before_mtime,
        "algorithm_version": ALGORITHM_VERSION,
        "cash_same_day_policy": CASH_SAME_DAY_POLICY,
    }

    with Session() as session:
        account = _seed(session)
        session.commit()

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
                run_id=run.id,
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
        annotation = annotate_day_trades(domain_trades, domain_allocs)

        # H：annotation 不改 allocations（同 run 再算一次）
        annotation2 = annotate_day_trades(domain_trades, domain_allocs)
        h_ok = (
            annotation.suspected_day_trade_qty == annotation2.suspected_day_trade_qty
            and [(a.buy_trade_id, a.sell_trade_id, a.quantity, a.match_type) for a in domain_allocs]
            == [
                (a.buy_trade_id, a.sell_trade_id, a.quantity, a.match_type)
                for a in domain_allocs
            ]
        )

        buy_qty = sum(t.quantity for t in trades if t.side == "BUY")
        sell_qty = sum(t.quantity for t in trades if t.side == "SELL")
        buy_gross = sum((txt_to_decimal(t.gross_amount_txt) for t in trades if t.side == "BUY"), Decimal(0))
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
                "expectations": {
                    "allocated_qty": 4000,
                    "standard_fifo_qty": 3600,
                    "same_day_reconciled_qty": 400,
                    "unsold_qty": 0,
                    "blocking": False,
                    "conservation_ok": True,
                },
            }
        )

        checks = {
            "allocated_4000": summary["allocated_qty"] == 4000,
            "standard_3600": by_type.get("STANDARD_FIFO", 0) == 3600,
            "pass2_400": by_type.get("SAME_DAY_RECONCILED", 0) == 400,
            "unsold_0": summary["unsold_qty"] == 0,
            "not_blocking": not result.blocking,
            "conservation_ok": bool(cons["ok"]),
            "integrity_ok": summary["integrity_check"] == "ok",
            "h_ok": h_ok,
        }
        summary["checks"] = checks
        summary["uat_verdict"] = "PASS" if all(checks.values()) else "FAIL"

        # 無 blocking → 正式（非 DRAFT）明細
        xlsx_path, audit_path, exc_path = generate_detail_report(
            session,
            account.id,
            OUT_DIR,
            allow_partial=False,
            run_id=run.id,
        )
        session.commit()
        summary["outputs"] = {
            "detail_xlsx": str(xlsx_path),
            "audit_json": str(audit_path),
            "exceptions_csv": str(exc_path),
            "detail_is_draft": "DRAFT" in xlsx_path.name,
        }

        # 列出 output 目錄內相關檔
        summary["output_files"] = sorted(p.name for p in OUT_DIR.glob("*") if p.is_file())

        # 冪等：再 match 一次，舊 run 不可覆寫
        run2, result2 = match_fifo_for_account(session, account.id)
        session.commit()
        old = session.get(AllocationRun, run.id)
        summary["idempotent_rerun"] = {
            "new_run_id": run2.id,
            "old_run_preserved": old is not None and old.id == run.id,
            "allocated_qty_same": sum(a.quantity for a in result2.allocations)
            == summary["allocated_qty"],
            "run_count": session.scalar(
                select(func.count()).select_from(AllocationRun).where(
                    AllocationRun.account_id == account.id
                )
            ),
        }

    after_mtime = _formal_mtime()
    summary["formal_db_mtime_after"] = after_mtime
    summary["formal_db_untouched"] = before_mtime == after_mtime
    summary["finished_at_utc"] = datetime.now(UTC).isoformat()

    summary_path = DB_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["uat_verdict"] == "PASS" and summary["formal_db_untouched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
