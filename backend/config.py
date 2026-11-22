"""應用程式路徑與預設設定。"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "trading.db"
PROFILES_DIR = PROJECT_ROOT / "configs" / "profiles"
SOURCE_ARCHIVE_DIR = PROJECT_ROOT / "data" / "source_archive"
BACKUP_DIR = PROJECT_ROOT / "data" / "backups"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"

ALGORITHM_VERSION = "fifo_v2_cash_prior_inventory"
REPORT_SCHEMA_VERSION = "detail_aw_v1"


def resolve_db_path(cli_path: str | None = None) -> Path:
    """依 CLI 參數或環境變數解析資料庫路徑。"""
    if cli_path:
        return Path(cli_path).expanduser().resolve()
    env = os.environ.get("TRADING_DB_PATH")
    if env:
        return Path(env).expanduser().resolve()
    return DEFAULT_DB_PATH.resolve()
