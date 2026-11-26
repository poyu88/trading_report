"""CR-06：2236 RCA 軌跡對齊之合成 E2E（seed→match→report→audit）。"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from backend.db.models import (
    Account,
    Broker,
    FifoAllocation,
    ImportBatch,
    RawRow,
    TradeRow,
)
from backend.domain.models import txt_to_decimal
from backend.services.allocation_service import match_fifo_for_account, quantity_conservation
from backend.services.day_trade_annotation import annotate_day_trades
from backend.services.report_service import generate_detail_report

# 與 RCA／UAT 同軌跡；金額由 fixture Decimal 獨立重算（不宣稱真實對帳單）
TRADES: list[tuple[str, str, int, str, str, str]] = [
    ("2024-08-05", "BUY", 2000, "100", "40", "0"),
    ("2024-08-12", "BUY", 1000, "105", "25", "0"),
    ("2024-08-20", "SELL", 400, "110", "20", "132"),
    ("2024-08-20", "SELL", 1000, "111", "30", "333"),
    ("2024-08-26", "SELL", 1000, "112", "30", "336"),
    ("2024-08-28", "SELL", 1000, "113", "30", "170"),
    ("2024-08-28", "BUY", 1000, "114", "25", "0"),
    ("2024-09-02", "SELL", 579, "115", "20", "200"),
    ("2024-09-02", "SELL", 21, "116", "5", "7"),
]


def _golden_from_fixture() -> dict[str, Decimal]:
    buy_gross = Decimal(0)
    sell_gross = Decimal(0)
    commission = Decimal(0)
    tax = Decimal(0)
    buy_qty = 0
    sell_qty = 0
    for _day, side, qty, price, comm, tax_s in TRADES:
        gross = Decimal(price) * qty
        commission += Decimal(comm)
        tax += Decimal(tax_s)
        if side == "BUY":
            buy_gross += gross
            buy_qty += qty
        else:
            sell_gross += gross
            sell_qty += qty
    return {
        "buy_qty": Decimal(buy_qty),
        "sell_qty": Decimal(sell_qty),
        "buy_gross": buy_gross,
        "sell_gross": sell_gross,
        "commission": commission,
        "tax": tax,
    }


def _seed(session) -> Account:
    broker = Broker(id=str(uuid.uuid4()), name=f"e2e-{uuid.uuid4().hex[:8]}")
    account = Account(id=str(uuid.uuid4()), broker_id=broker.id, account_label="e2e2236")
    batch = ImportBatch(
        id=str(uuid.uuid4()),
        account_id=account.id,
        file_sha256="c" * 64,
        filename="synthetic_2236_e2e.xls",
        profile_id="statement_html_v1",
        profile_version=1,
        status="completed",
    )
    session.add_all([broker, account, batch])
    session.flush()
    for idx, (day, side, qty, price, commission, tax) in enumerate(TRADES, start=1):
        raw = RawRow(
            id=str(uuid.uuid4()),
            batch_id=batch.id,
            sheet_name="Sheet1",
            row_index=idx,
            raw_json="{}",
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
            gross_amount_txt=str(Decimal(price) * qty),
            commission_txt=commission,
            tax_txt=tax,
            interest_txt="0",
            raw_payload_json="{}",
        )
        session.add_all([raw, trade])
    session.flush()
    return account


def test_cr06_2236_synthetic_e2e_seed_match_report_audit(db_session, tmp_path: Path) -> None:
    """BUY/SELL 4000、Pass1 3600、Pass2 400、unsold/unmatched 0、suspected≤1000。"""
    golden = _golden_from_fixture()
    account = _seed(db_session)
    db_session.commit()

    run, result = match_fifo_for_account(db_session, account.id)
    db_session.commit()

    trades = list(db_session.scalars(select(TradeRow).where(TradeRow.account_id == account.id)))
    alloc_rows = list(
        db_session.scalars(select(FifoAllocation).where(FifoAllocation.run_id == run.id))
    )
    buy_qty = sum(t.quantity for t in trades if t.side == "BUY")
    sell_qty = sum(t.quantity for t in trades if t.side == "SELL")
    assert buy_qty == int(golden["buy_qty"]) == 4000
    assert sell_qty == int(golden["sell_qty"]) == 4000

    by_type: dict[str, int] = {}
    for a in result.allocations:
        by_type[a.match_type] = by_type.get(a.match_type, 0) + a.quantity
    assert by_type.get("STANDARD_FIFO", 0) == 3600
    assert by_type.get("SAME_DAY_RECONCILED", 0) == 400
    assert sum(a.quantity for a in result.allocations) == 4000
    assert result.unsold == []
    assert not result.blocking
    assert not any(i.issue_code == "INSUFFICIENT_PRIOR_BUYS" for i in result.issues)

    cons = quantity_conservation(trades, alloc_rows)
    assert cons["ok"]

    buy_gross = sum(
        (txt_to_decimal(t.gross_amount_txt) for t in trades if t.side == "BUY"), Decimal(0)
    )
    sell_gross = sum(
        (txt_to_decimal(t.gross_amount_txt) for t in trades if t.side == "SELL"), Decimal(0)
    )
    commission = sum((txt_to_decimal(t.commission_txt) for t in trades), Decimal(0))
    tax = sum((txt_to_decimal(t.tax_txt) for t in trades), Decimal(0))
    assert buy_gross == golden["buy_gross"]
    assert sell_gross == golden["sell_gross"]
    assert commission == golden["commission"]
    assert tax == golden["tax"]

    from datetime import date

    from backend.domain.models import Allocation, Trade

    domain_trades = [
        Trade(
            trade_id=t.id,
            account_id=t.account_id,
            source_row_id=t.raw_row_id,
            symbol=t.symbol,
            name=t.name,
            trade_date=date.fromisoformat(t.trade_date),
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
    ann = annotate_day_trades(domain_trades, domain_allocs)
    assert ann.suspected_day_trade_qty <= 1000
    assert ann.same_day_reconciled_qty == 400

    out = tmp_path / "out"
    xlsx, audit_path, exc_path = generate_detail_report(
        db_session, account.id, out, run_id=run.id, allow_partial=False
    )
    db_session.commit()
    assert xlsx.exists() and audit_path.exists() and exc_path.exists()
    assert "DRAFT" not in xlsx.name
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert "day_trade_annotation" in audit
    assert audit["day_trade_annotation"]["suspected_day_trade_qty"] <= 1000
    cand0 = audit["day_trade_annotation"]["candidates"][0]
    assert "candidate_sell_trade_ids" in cand0
    assert "half_rate_sell_qty" in cand0
    assert "tax_rule_version" in cand0
