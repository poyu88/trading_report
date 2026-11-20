"""本機 CLI：db / import / match / report / audit。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from alembic.config import Config

from alembic import command
from backend.config import DEFAULT_OUTPUT_DIR, PROJECT_ROOT, resolve_db_path
from backend.db.repositories import find_account_by_label
from backend.db.session import create_db_engine, init_db, integrity_check, make_session_factory
from backend.domain.exceptions import BlockingExceptionError, TradingReportError
from backend.services.allocation_service import match_fifo_for_account
from backend.services.backup_service import backup_database
from backend.services.import_service import apply_import, preview_import, preview_to_dict
from backend.services.reconciliation import build_audit
from backend.services.report_service import generate_detail_report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trading-report", description="股票交易報表系統 CLI")
    db_parent = argparse.ArgumentParser(add_help=False)
    db_parent.add_argument("--db", default=None, help="SQLite 路徑（或設 TRADING_DB_PATH）")
    parser.add_argument("--db", default=None, help="SQLite 路徑（或設 TRADING_DB_PATH）")
    sub = parser.add_subparsers(dest="command", required=True)

    db = sub.add_parser("db", help="資料庫操作", parents=[db_parent])
    db_sub = db.add_subparsers(dest="db_command", required=True)
    db_sub.add_parser("init", help="初始化 schema", parents=[db_parent])
    p_backup = db_sub.add_parser("backup", help="備份資料庫", parents=[db_parent])
    p_backup.add_argument("--output-dir", default=None)

    imp = sub.add_parser("import", help="匯入交易", parents=[db_parent])
    imp_sub = imp.add_subparsers(dest="import_command", required=True)
    p_prev = imp_sub.add_parser("preview", help="預覽（不入庫）", parents=[db_parent])
    p_prev.add_argument("--file", required=True)
    p_prev.add_argument("--profile", required=True)
    p_apply = imp_sub.add_parser("apply", help="入庫", parents=[db_parent])
    p_apply.add_argument("--file", required=True)
    p_apply.add_argument("--broker", required=True)
    p_apply.add_argument("--account", required=True)
    p_apply.add_argument("--profile", required=True)

    match = sub.add_parser("match", help="配對", parents=[db_parent])
    match_sub = match.add_subparsers(dest="match_command", required=True)
    p_fifo = match_sub.add_parser("fifo", help="執行 FIFO", parents=[db_parent])
    p_fifo.add_argument("--account", required=True, help="帳戶標籤")

    report = sub.add_parser("report", help="報表", parents=[db_parent])
    report_sub = report.add_subparsers(dest="report_command", required=True)
    p_detail = report_sub.add_parser("detail", help="交易明細", parents=[db_parent])
    p_detail.add_argument("--account", required=True)
    p_detail.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    p_detail.add_argument("--allow-partial", action="store_true")

    p_audit = sub.add_parser("audit", help="稽核摘要", parents=[db_parent])
    p_audit.add_argument("--account", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    db_path = resolve_db_path(args.db)

    try:
        if args.command == "db":
            return _cmd_db(args, db_path)
        if args.command == "import":
            return _cmd_import(args, db_path)
        if args.command == "match":
            return _cmd_match(args, db_path)
        if args.command == "report":
            return _cmd_report(args, db_path)
        if args.command == "audit":
            return _cmd_audit(args, db_path)
        parser.error(f"未知命令：{args.command}")
        return 2
    except TradingReportError as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"未預期錯誤：{exc}", file=sys.stderr)
        return 1


def _session(db_path: Path):
    engine = create_db_engine(db_path)
    return make_session_factory(engine)()


def _cmd_db(args: argparse.Namespace, db_path: Path) -> int:
    if args.db_command == "init":
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # 以 Alembic migration 建表（測試可用 backend.db.session.init_db）
        os.environ["TRADING_DB_PATH"] = str(db_path.resolve())
        cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
        cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.resolve().as_posix()}")
        command.upgrade(cfg, "head")
        engine = create_db_engine(db_path)
        check = integrity_check(engine)
        print(f"資料庫已初始化：{db_path}")
        print(f"integrity_check={check}")
        return 0
    if args.db_command == "backup":
        out = Path(args.output_dir) if args.output_dir else None
        dest = backup_database(db_path, out)
        print(f"備份完成：{dest}")
        return 0
    return 2


def _cmd_import(args: argparse.Namespace, db_path: Path) -> int:
    path = Path(args.file)
    if args.import_command == "preview":
        preview = preview_import(path, args.profile)
        print(json.dumps(preview_to_dict(preview), ensure_ascii=False, indent=2))
        print(
            f"摘要：交易 {preview.trade_count}（買 {preview.buy_count}／賣 {preview.sell_count}），"
            f"排除 {preview.excluded_count}，錯誤 {preview.error_count}，格式 {preview.file_kind}"
        )
        return 0
    if args.import_command == "apply":
        # 確保 DB 存在
        if not db_path.exists():
            init_db(db_path)
        session = _session(db_path)
        try:
            result = apply_import(session, path, args.broker, args.account, args.profile)
            session.commit()
            print(
                json.dumps(
                    {
                        "batch_id": result.batch_id,
                        "already_imported": result.already_imported,
                        "trade_count": result.trade_count,
                        "excluded_count": result.excluded_count,
                        "error_count": result.error_count,
                        "message": result.message,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    return 2


def _resolve_account_id(session, label: str) -> str:
    account = find_account_by_label(session, label)
    if not account:
        raise TradingReportError(f"找不到帳戶標籤：{label}")
    return account.id


def _cmd_match(args: argparse.Namespace, db_path: Path) -> int:
    if args.match_command != "fifo":
        return 2
    session = _session(db_path)
    try:
        account_id = _resolve_account_id(session, args.account)
        run, result = match_fifo_for_account(session, account_id)
        session.commit()
        print(
            json.dumps(
                {
                    "run_id": run.id,
                    "status": run.status,
                    "allocations": len(result.allocations),
                    "issues": len(result.issues),
                    "blocking": result.blocking,
                    "unsold_lots": len(result.unsold),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _cmd_report(args: argparse.Namespace, db_path: Path) -> int:
    if args.report_command != "detail":
        return 2
    session = _session(db_path)
    try:
        account_id = _resolve_account_id(session, args.account)
        xlsx, audit, exc = generate_detail_report(
            session,
            account_id,
            Path(args.output_dir),
            allow_partial=args.allow_partial,
        )
        session.commit()
        print(f"明細報表：{xlsx}")
        print(f"稽核檔：{audit}")
        print(f"例外檔：{exc}")
        return 0
    except BlockingExceptionError as exc:
        session.rollback()
        print(f"錯誤：{exc}", file=sys.stderr)
        return 1
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _cmd_audit(args: argparse.Namespace, db_path: Path) -> int:
    session = _session(db_path)
    try:
        account_id = _resolve_account_id(session, args.account)
        summary = build_audit(session, account_id)
        print(
            json.dumps(
                {
                    "account_id": summary.account_id,
                    "run_id": summary.run_id,
                    "trade_count": summary.trade_count,
                    "buy_count": summary.buy_count,
                    "sell_count": summary.sell_count,
                    "allocation_count": summary.allocation_count,
                    "issue_count": summary.issue_count,
                    "blocking_issue_count": summary.blocking_issue_count,
                    "conservation_ok": summary.conservation_ok,
                    "commission_total": summary.commission_total,
                    "tax_total": summary.tax_total,
                    "issues": summary.issues,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
