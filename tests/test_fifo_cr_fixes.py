"""PR #7 Code Review 修正：版本追溯、期初庫存守恆、fingerprint（合成資料）。"""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from backend.config import ALGORITHM_VERSION
from backend.db.models import (
    Account,
    AllocationRun,
    Broker,
    FifoAllocation,
    ImportBatch,
    OpeningLotRow,
    RawRow,
    TradeRow,
)
from backend.domain.models import OpeningLot
from backend.services.allocation_service import match_fifo_for_account, quantity_conservation
from backend.services.fifo_matcher import MatchInputTrade, input_fingerprint, run_fifo
from backend.services.reconciliation import build_audit


def _seed_account(session, label: str = "main") -> Account:
    broker = Broker(id=str(uuid.uuid4()), name=f"broker-{uuid.uuid4().hex[:8]}")
    account = Account(id=str(uuid.uuid4()), broker_id=broker.id, account_label=label)
    batch = ImportBatch(
        id=str(uuid.uuid4()),
        account_id=account.id,
        file_sha256="a" * 64,
        filename="synthetic.xls",
        profile_id="statement_html_v1",
        profile_version=1,
        status="completed",
    )
    session.add_all([broker, account, batch])
    session.flush()
    return account


def _add_trade(
    session,
    *,
    account: Account,
    batch_id: str,
    row_index: int,
    side: str,
    qty: int,
    price: str,
    day: str = "2025-03-20",
    symbol: str = "1589",
    trade_type: str = "CASH",
) -> TradeRow:
    raw = RawRow(
        id=str(uuid.uuid4()),
        batch_id=batch_id,
        sheet_name="",
        row_index=row_index,
        raw_json="{}",
        row_sha256=uuid.uuid4().hex + uuid.uuid4().hex[:32],
        parse_status="ok",
    )
    trade = TradeRow(
        id=str(uuid.uuid4()),
        raw_row_id=raw.id,
        account_id=account.id,
        symbol=symbol,
        name="synthetic",
        trade_date=day,
        side=side,
        trade_type=trade_type,
        currency="TWD",
        quantity=qty,
        unit_price_txt=price,
        gross_amount_txt=str(Decimal(price) * qty),
        commission_txt="0",
        tax_txt="0",
        interest_txt="0",
        raw_payload_json="{}",
    )
    session.add_all([raw, trade])
    session.flush()
    return trade


def _add_opening(
    session,
    *,
    account: Account,
    qty: int,
    cost: str,
    status: str = "approved",
    symbol: str = "1589",
    buy_date: str = "2023-02-03",
) -> OpeningLotRow:
    lot = OpeningLotRow(
        id=str(uuid.uuid4()),
        account_id=account.id,
        symbol=symbol,
        currency="TWD",
        buy_date=buy_date,
        quantity=qty,
        unit_cost_txt=cost,
        approval_note="synthetic approved",
        status=status,
    )
    session.add(lot)
    session.flush()
    return lot


def _mit(
    tid: str,
    day: str,
    side: str,
    qty: int,
    price: str,
    *,
    account: str = "acc1",
    source_order: int = 0,
    symbol: str = "1111",
) -> MatchInputTrade:
    return MatchInputTrade(
        trade_id=tid,
        account_id=account,
        symbol=symbol,
        trade_date=date.fromisoformat(day),
        trade_time=None,
        trade_sequence=None,
        side=side,
        trade_type="CASH",
        currency="TWD",
        quantity=qty,
        unit_price=Decimal(price),
        source_order=source_order,
    )


# --- CR-01：演算法版本追溯 ---


def test_cr01_algorithm_version_is_cash_prior_inventory_v2() -> None:
    assert ALGORITHM_VERSION == "fifo_v2_cash_prior_inventory"


def test_cr01_new_run_writes_version_and_policy(db_session) -> None:
    account = _seed_account(db_session)
    batch_id = db_session.scalar(
        select(ImportBatch.id).where(ImportBatch.account_id == account.id)
    )
    assert batch_id is not None
    _add_opening(db_session, account=account, qty=1000, cost="60")
    _add_trade(
        db_session,
        account=account,
        batch_id=batch_id,
        row_index=1,
        side="SELL",
        qty=1000,
        price="70",
    )
    db_session.commit()

    run, result = match_fifo_for_account(db_session, account.id)
    db_session.commit()
    assert not result.blocking
    assert run.algorithm_version == "fifo_v2_cash_prior_inventory"
    cfg = json.loads(run.config_json)
    assert cfg.get("cash_same_day_policy") == "prior_inventory_first"


def test_cr01_rerun_keeps_old_run_immutable(db_session) -> None:
    account = _seed_account(db_session)
    batch_id = db_session.scalar(
        select(ImportBatch.id).where(ImportBatch.account_id == account.id)
    )
    assert batch_id is not None
    _add_trade(
        db_session,
        account=account,
        batch_id=batch_id,
        row_index=1,
        side="BUY",
        qty=100,
        price="10",
        day="2025-01-01",
    )
    _add_trade(
        db_session,
        account=account,
        batch_id=batch_id,
        row_index=2,
        side="SELL",
        qty=100,
        price="12",
        day="2025-01-02",
    )
    db_session.commit()

    run1, _ = match_fifo_for_account(db_session, account.id)
    db_session.commit()
    old_id = run1.id
    old_version = run1.algorithm_version
    old_fp = run1.input_fingerprint
    old_allocs = list(
        db_session.scalars(select(FifoAllocation).where(FifoAllocation.run_id == old_id))
    )
    old_qty = sorted(a.allocated_quantity for a in old_allocs)

    run2, _ = match_fifo_for_account(db_session, account.id)
    db_session.commit()
    assert run2.id != old_id

    kept = db_session.get(AllocationRun, old_id)
    assert kept is not None
    assert kept.algorithm_version == old_version
    assert kept.input_fingerprint == old_fp
    kept_allocs = list(
        db_session.scalars(select(FifoAllocation).where(FifoAllocation.run_id == old_id))
    )
    assert sorted(a.allocated_quantity for a in kept_allocs) == old_qty
    versions = {
        r.algorithm_version
        for r in db_session.scalars(
            select(AllocationRun).where(AllocationRun.account_id == account.id)
        )
    }
    assert "fifo_v2_cash_prior_inventory" in versions


# --- CR-02：期初庫存數量守恆 ---


def test_cr02_conservation_ok_opening_only_covers_sell() -> None:
    """opening 1000 + SELL 1000、無 BUY → conservation ok。"""
    trades = [
        TradeRow(
            id="s1",
            raw_row_id="r1",
            account_id="acc",
            symbol="1589",
            trade_date="2025-03-20",
            side="SELL",
            trade_type="CASH",
            currency="TWD",
            quantity=1000,
            unit_price_txt="70",
            gross_amount_txt="70000",
            commission_txt="0",
            tax_txt="0",
            interest_txt="0",
            raw_payload_json="{}",
        )
    ]
    allocations = [
        FifoAllocation(
            id="a1",
            run_id="run",
            buy_trade_id=None,
            opening_lot_id="ol1",
            sell_trade_id="s1",
            allocated_quantity=1000,
            sequence_no=1,
        )
    ]
    openings = [
        OpeningLot(
            lot_id="ol1",
            account_id="acc",
            symbol="1589",
            currency="TWD",
            buy_date=date(2023, 2, 3),
            quantity=1000,
            unit_cost=Decimal(60),
            approval_note="ok",
        )
    ]
    cons = quantity_conservation(trades, allocations, opening_lots=openings)
    assert cons["ok"] is True
    assert cons["opening_qty"] == 1000
    assert cons["buy_qty"] == 0
    assert cons["supply_qty"] == 1000
    assert cons["allocated_qty"] == 1000
    assert cons["sold_from_openings"] == 1000
    assert cons["sold_from_buys"] == 0


def test_cr02_unapproved_opening_not_in_supply() -> None:
    trades = [
        TradeRow(
            id="s1",
            raw_row_id="r1",
            account_id="acc",
            symbol="1589",
            trade_date="2025-03-20",
            side="SELL",
            trade_type="CASH",
            currency="TWD",
            quantity=1000,
            unit_price_txt="70",
            gross_amount_txt="70000",
            commission_txt="0",
            tax_txt="0",
            interest_txt="0",
            raw_payload_json="{}",
        )
    ]
    allocations = [
        FifoAllocation(
            id="a1",
            run_id="run",
            buy_trade_id=None,
            opening_lot_id="ol_pending",
            sell_trade_id="s1",
            allocated_quantity=1000,
            sequence_no=1,
        )
    ]
    # 呼叫端只應傳入 approved；未核准 lot 不應計入 supply
    cons = quantity_conservation(trades, allocations, opening_lots=[])
    assert cons["ok"] is False
    assert cons["opening_qty"] == 0
    assert cons["supply_qty"] == 0


def test_cr02_over_allocate_opening_fails() -> None:
    trades = [
        TradeRow(
            id="s1",
            raw_row_id="r1",
            account_id="acc",
            symbol="1589",
            trade_date="2025-03-20",
            side="SELL",
            trade_type="CASH",
            currency="TWD",
            quantity=1500,
            unit_price_txt="70",
            gross_amount_txt="105000",
            commission_txt="0",
            tax_txt="0",
            interest_txt="0",
            raw_payload_json="{}",
        )
    ]
    allocations = [
        FifoAllocation(
            id="a1",
            run_id="run",
            buy_trade_id=None,
            opening_lot_id="ol1",
            sell_trade_id="s1",
            allocated_quantity=1500,
            sequence_no=1,
        )
    ]
    openings = [
        OpeningLot(
            lot_id="ol1",
            account_id="acc",
            symbol="1589",
            currency="TWD",
            buy_date=date(2023, 2, 3),
            quantity=1000,
            unit_cost=Decimal(60),
            approval_note="ok",
        )
    ]
    cons = quantity_conservation(trades, allocations, opening_lots=openings)
    assert cons["ok"] is False


def test_cr02_build_audit_includes_approved_opening(db_session) -> None:
    account = _seed_account(db_session)
    batch_id = db_session.scalar(
        select(ImportBatch.id).where(ImportBatch.account_id == account.id)
    )
    assert batch_id is not None
    _add_opening(db_session, account=account, qty=1000, cost="60")
    _add_trade(
        db_session,
        account=account,
        batch_id=batch_id,
        row_index=1,
        side="SELL",
        qty=1000,
        price="70",
    )
    db_session.commit()
    run, result = match_fifo_for_account(db_session, account.id)
    db_session.commit()
    assert not result.blocking
    audit = build_audit(db_session, account.id, run.id)
    assert audit.conservation_ok is True


# --- CR-03：fingerprint 與排序語意 ---


def test_cr03_fingerprint_includes_source_order_and_account() -> None:
    t1 = _mit("t1", "2025-03-20", "SELL", 100, "70", account="accA", source_order=1)
    t2 = _mit("t1", "2025-03-20", "SELL", 100, "70", account="accA", source_order=2)
    lots = [
        OpeningLot(
            lot_id="ol1",
            account_id="accA",
            symbol="1111",
            currency="TWD",
            buy_date=date(2024, 1, 1),
            quantity=100,
            unit_cost=Decimal(60),
            approval_note="ok",
        )
    ]
    fp1 = input_fingerprint([t1], lots)
    fp2 = input_fingerprint([t2], lots)
    assert fp1 != fp2

    t_other_acc = _mit("t1", "2025-03-20", "SELL", 100, "70", account="accB", source_order=1)
    assert input_fingerprint([t1], lots) != input_fingerprint([t_other_acc], lots)

    lots_usd = [
        OpeningLot(
            lot_id="ol1",
            account_id="accA",
            symbol="1111",
            currency="USD",
            buy_date=date(2024, 1, 1),
            quantity=100,
            unit_cost=Decimal(60),
            approval_note="ok",
        )
    ]
    assert input_fingerprint([t1], lots) != input_fingerprint([t1], lots_usd)


def test_cr03_same_day_multi_sell_order_is_deterministic() -> None:
    """缺可信序時：source_order 決定同日多 SELL 配對順序，結果可重現。"""
    lots = [
        OpeningLot(
            lot_id="ol1",
            account_id="acc1",
            symbol="1111",
            currency="TWD",
            buy_date=date(2024, 1, 1),
            quantity=1500,
            unit_cost=Decimal(50),
            approval_note="ok",
        )
    ]
    trades_a = [
        _mit("s_hi", "2025-03-20", "SELL", 1000, "80", source_order=1),
        _mit("s_lo", "2025-03-20", "SELL", 500, "60", source_order=2),
        _mit("b1", "2025-03-20", "BUY", 1000, "72", source_order=3),
    ]
    trades_b = [
        _mit("s_lo", "2025-03-20", "SELL", 500, "60", source_order=1),
        _mit("s_hi", "2025-03-20", "SELL", 1000, "80", source_order=2),
        _mit("b1", "2025-03-20", "BUY", 1000, "72", source_order=3),
    ]
    r1 = run_fifo("r1", trades_a, lots)
    r1b = run_fifo("r1b", trades_a, lots)
    r2 = run_fifo("r2", trades_b, lots)

    assert not r1.blocking and not r2.blocking
    keys1 = sorted(
        (a.sell_trade_id, a.opening_lot_id, a.quantity, a.sequence_no) for a in r1.allocations
    )
    keys1b = sorted(
        (a.sell_trade_id, a.opening_lot_id, a.quantity, a.sequence_no) for a in r1b.allocations
    )
    assert keys1 == keys1b
    # 同日多 SELL 排列改變時，sequence 對應的賣出不同 → 逐筆成本／損益路徑不同
    seq_sell_1 = {a.sequence_no: a.sell_trade_id for a in r1.allocations}
    seq_sell_2 = {a.sequence_no: a.sell_trade_id for a in r2.allocations}
    assert seq_sell_1 != seq_sell_2
    assert sum(a.quantity for a in r1.allocations) == sum(a.quantity for a in r2.allocations)
    assert sum(u.available for u in r1.unsold) == sum(u.available for u in r2.unsold) == 1000
