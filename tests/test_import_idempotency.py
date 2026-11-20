"""DB 去重與入庫。"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select

from backend.db.models import TradeRow
from backend.services.import_service import apply_import


def _copy_fixture(fixtures_dir: Path, tmp_path: Path, name: str = "statement_sample.html") -> Path:
    src = fixtures_dir / name
    dest = tmp_path / "import.xls"
    dest.write_bytes(src.read_bytes())
    return dest


def test_reimport_same_file_no_new_trades(db_session, fixtures_dir: Path, tmp_path: Path) -> None:
    path = _copy_fixture(fixtures_dir, tmp_path)
    r1 = apply_import(db_session, path, "群益", "main", "statement_html_v1")
    db_session.commit()
    assert r1.already_imported is False
    assert r1.trade_count == 5

    r2 = apply_import(db_session, path, "群益", "main", "statement_html_v1")
    db_session.commit()
    assert r2.already_imported is True
    assert r2.batch_id == r1.batch_id

    total = db_session.scalar(select(func.count()).select_from(TradeRow))
    assert total == 5
