"""pytest fixtures。"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.db.session import init_db, make_session_factory


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test.db"
    engine = init_db(db_path)
    Session = make_session_factory(engine)
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture()
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"
