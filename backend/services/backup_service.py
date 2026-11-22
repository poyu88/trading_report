"""SQLite 備份。"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from backend.config import BACKUP_DIR


def backup_database(
    db_path: Path,
    output_dir: Path | None = None,
    *,
    readonly_source: bool = True,
    dest_name: str | None = None,
) -> Path:
    """以 SQLite Backup API 複製資料庫。

    預設以 `mode=ro` 開啟來源，避免誤寫正式庫；仍會寫入 dest。
    """
    src = Path(db_path)
    if not src.is_file():
        raise FileNotFoundError(f"資料庫不存在：{src}")
    dest_dir = output_dir or BACKUP_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = dest_dir / (dest_name or f"trading_backup_{stamp}.db")

    if readonly_source:
        uri = f"file:{src.resolve().as_posix()}?mode=ro"
        source_cm = sqlite3.connect(uri, uri=True)
    else:
        source_cm = sqlite3.connect(src)

    with source_cm as source, sqlite3.connect(dest) as target:
        source.backup(target)
    return dest
