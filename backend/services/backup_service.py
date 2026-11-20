"""SQLite 備份。"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from backend.config import BACKUP_DIR


def backup_database(db_path: Path, output_dir: Path | None = None) -> Path:
    src = Path(db_path)
    if not src.is_file():
        raise FileNotFoundError(f"資料庫不存在：{src}")
    dest_dir = output_dir or BACKUP_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = dest_dir / f"trading_backup_{stamp}.db"

    with sqlite3.connect(src) as source, sqlite3.connect(dest) as target:
        source.backup(target)
    return dest
