"""SQLite session 工廠。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.db.models import Base


def _sqlite_url(db_path: Path) -> str:
    return f"sqlite:///{db_path.as_posix()}"


def create_db_engine(db_path: Path) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        _sqlite_url(db_path),
        connect_args={"check_same_thread": False},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
        except sqlite3.Error:
            # 部分檔案系統不支援 WAL，維持預設 journal 即可
            pass
        cursor.close()

    return engine


def init_db(db_path: Path) -> Engine:
    """建立 schema（開發／測試用；正式可用 Alembic）。"""
    engine = create_db_engine(db_path)
    Base.metadata.create_all(engine)
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def integrity_check(engine: Engine) -> str:
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA integrity_check")).scalar_one()
        return str(result)
