"""CR-05：match_type migration upgrade／backfill／downgrade／re-upgrade。"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command
from backend.config import PROJECT_ROOT

PREV_REV = "a1b2c3d4e5f6"
HEAD_REV = "b2c3d4e5f6a7"


def _alembic_cfg(db_path: Path) -> Config:
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    return cfg


def _seed_pre_match_type(engine) -> None:
    """在尚無 match_type 的 schema 植入 CASH／DAY_TRADE 配對列。"""
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO brokers (id, name) VALUES ('br1', 'mig-broker')"))
        conn.execute(
            text(
                "INSERT INTO accounts (id, broker_id, account_label) VALUES ('ac1', 'br1', 'mig')"
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO import_batches (
                    id, account_id, file_sha256, filename, profile_id, profile_version,
                    imported_at_utc, status
                ) VALUES (
                    'bat1', 'ac1', :sha, 'mig.xls', 'statement_html_v1', 1,
                    '2024-01-01T00:00:00+00:00', 'completed'
                )
                """
            ),
            {"sha": "a" * 64},
        )
        for rid, idx in (("raw_b", 1), ("raw_s_cash", 2), ("raw_db", 3), ("raw_ds", 4)):
            conn.execute(
                text(
                    """
                    INSERT INTO raw_rows (
                        id, batch_id, sheet_name, row_index, raw_json, row_sha256, parse_status
                    ) VALUES (:id, 'bat1', 'S', :idx, '{}', :sha, 'ok')
                    """
                ),
                {"id": rid, "idx": idx, "sha": (rid + "x" * 64)[:64]},
            )

        def _trade(
            tid: str,
            raw_id: str,
            *,
            side: str,
            trade_type: str,
            day: str = "2025-01-10",
        ) -> None:
            conn.execute(
                text(
                    """
                    INSERT INTO trades (
                        id, raw_row_id, account_id, symbol, name, trade_date, trade_time,
                        trade_sequence, side, trade_type, currency, quantity,
                        unit_price_txt, gross_amount_txt, commission_txt, tax_txt,
                        interest_txt, net_settlement_txt, external_trade_id, raw_payload_json
                    ) VALUES (
                        :id, :raw, 'ac1', '2330', NULL, :day, NULL, NULL,
                        :side, :tt, 'TWD', 100,
                        '100', '10000', '20', '0', '0', NULL, NULL, '{}'
                    )
                    """
                ),
                {"id": tid, "raw": raw_id, "side": side, "tt": trade_type, "day": day},
            )

        _trade("t_buy_cash", "raw_b", side="BUY", trade_type="CASH", day="2025-01-09")
        _trade("t_sell_cash", "raw_s_cash", side="SELL", trade_type="CASH")
        _trade("t_buy_dt", "raw_db", side="BUY", trade_type="DAY_TRADE")
        _trade("t_sell_dt", "raw_ds", side="SELL", trade_type="DAY_TRADE")

        conn.execute(
            text(
                """
                INSERT INTO allocation_runs (
                    id, algorithm_version, input_fingerprint, started_at_utc,
                    finished_at_utc, status, config_json, account_id
                ) VALUES (
                    'run1', 'fifo_v2', :fp, '2025-01-10T00:00:00+00:00',
                    '2025-01-10T00:00:01+00:00', 'completed', '{}', 'ac1'
                )
                """
            ),
            {"fp": "b" * 64},
        )
        # 無 match_type 欄：CASH 配對 + DAY_TRADE 配對
        conn.execute(
            text(
                """
                INSERT INTO fifo_allocations (
                    id, run_id, buy_trade_id, opening_lot_id, sell_trade_id,
                    allocated_quantity, sequence_no
                ) VALUES
                    ('a_cash', 'run1', 't_buy_cash', NULL, 't_sell_cash', 100, 1),
                    ('a_dt', 'run1', 't_buy_dt', NULL, 't_sell_dt', 100, 2)
                """
            )
        )


def test_match_type_migration_backfill_day_trade_and_roundtrip(tmp_path: Path) -> None:
    """upgrade → DAY_TRADE 列標記／CASH 維持 STANDARD → downgrade → re-upgrade。"""
    db_path = tmp_path / "mig.db"
    cfg = _alembic_cfg(db_path)

    command.upgrade(cfg, PREV_REV)
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    _seed_pre_match_type(engine)

    with engine.connect() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(fifo_allocations)")).all()}
        assert "match_type" not in cols
        assert conn.execute(text("SELECT COUNT(*) FROM fifo_allocations")).scalar() == 2

    command.upgrade(cfg, HEAD_REV)

    with engine.connect() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(fifo_allocations)")).all()}
        assert "match_type" in cols
        rows = {
            r[0]: r[1]
            for r in conn.execute(
                text("SELECT id, match_type FROM fifo_allocations ORDER BY id")
            ).all()
        }
        assert rows["a_cash"] == "STANDARD_FIFO"
        assert rows["a_dt"] == "DAY_TRADE_FIFO"
        # FK 仍可 join
        join_n = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM fifo_allocations a
                JOIN trades t ON t.id = a.sell_trade_id
                WHERE a.match_type = 'DAY_TRADE_FIFO' AND t.trade_type = 'DAY_TRADE'
                """
            )
        ).scalar()
        assert join_n == 1

    command.downgrade(cfg, PREV_REV)
    with engine.connect() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(fifo_allocations)")).all()}
        assert "match_type" not in cols
        assert conn.execute(text("SELECT COUNT(*) FROM fifo_allocations")).scalar() == 2

    command.upgrade(cfg, HEAD_REV)
    with engine.connect() as conn:
        rows = {
            r[0]: r[1]
            for r in conn.execute(
                text("SELECT id, match_type FROM fifo_allocations ORDER BY id")
            ).all()
        }
        assert rows["a_cash"] == "STANDARD_FIFO"
        assert rows["a_dt"] == "DAY_TRADE_FIFO"


def test_migration_db_path_isolated_from_formal(tmp_path: Path) -> None:
    """防呆：migration 測資路徑必須落在 tmp，不得等於正式 trading.db。"""
    formal = (PROJECT_ROOT / "data" / "trading.db").resolve()
    db_path = (tmp_path / "mig.db").resolve()
    assert db_path != formal
    assert formal not in db_path.parents
    assert "trading.db" not in str(db_path)
