"""原始交易 ↔ 片段股數／價金／費用守恆核對表。"""

from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from backend.reports.detail_projector import AllocationView, FifoTraceRow, TradeView
from backend.reports.detail_writer import unique_output_path
from backend.services.report_finance import split_sell_gross_with_residual


def write_conservation_csv(
    trades: list[TradeView],
    allocations: list[AllocationView],
    trace_rows: list[FifoTraceRow],
    output_dir: Path,
    *,
    when: datetime | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = (when or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
    path = unique_output_path(output_dir / f"價金費用守恆核對_{stamp}.csv")

    sell_allocs: dict[str, list[AllocationView]] = {}
    for a in allocations:
        sell_allocs.setdefault(a.sell_trade_id, []).append(a)

    fieldnames = [
        "trade_id",
        "side",
        "symbol",
        "trade_date",
        "source_qty",
        "matched_qty",
        "unmatched_or_unsold_qty",
        "source_gross",
        "matched_gross",
        "residual_gross",
        "gross_ok",
        "commission",
        "tax",
        "interest",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for t in sorted(trades, key=lambda x: (x.symbol, x.trade_date, x.trade_id)):
            if t.side == "SELL":
                alist = sell_allocs.get(t.trade_id, [])
                matched_parts, unmatched_gross, unmatched_qty = split_sell_gross_with_residual(
                    t.quantity,
                    t.gross_amount,
                    [a.quantity for a in alist],
                )
                matched_qty = sum(a.quantity for a in alist)
                matched_gross = sum(matched_parts, Decimal(0))
                residual = unmatched_gross or Decimal(0)
                writer.writerow(
                    {
                        "trade_id": t.trade_id,
                        "side": t.side,
                        "symbol": t.symbol,
                        "trade_date": t.trade_date.isoformat(),
                        "source_qty": t.quantity,
                        "matched_qty": matched_qty,
                        "unmatched_or_unsold_qty": unmatched_qty,
                        "source_gross": str(t.gross_amount),
                        "matched_gross": str(matched_gross),
                        "residual_gross": str(residual),
                        "gross_ok": str(matched_gross + residual == t.gross_amount),
                        "commission": str(t.commission),
                        "tax": str(t.tax),
                        "interest": str(t.interest),
                    }
                )
            else:
                sold = sum(a.quantity for a in allocations if a.buy_trade_id == t.trade_id)
                unsold_qty = t.quantity - sold
                buy_frags = [
                    r
                    for r in trace_rows
                    if r.buy_trade_id == t.trade_id and r.row_kind in ("MATCHED", "UNSOLD_BUY")
                ]
                frag_gross = sum((r.gross_amount or Decimal(0) for r in buy_frags), Decimal(0))
                writer.writerow(
                    {
                        "trade_id": t.trade_id,
                        "side": t.side,
                        "symbol": t.symbol,
                        "trade_date": t.trade_date.isoformat(),
                        "source_qty": t.quantity,
                        "matched_qty": sold,
                        "unmatched_or_unsold_qty": unsold_qty,
                        "source_gross": str(t.gross_amount),
                        "matched_gross": str(frag_gross),
                        "residual_gross": "",
                        "gross_ok": str(frag_gross == t.gross_amount),
                        "commission": str(t.commission),
                        "tax": str(t.tax),
                        "interest": str(t.interest),
                    }
                )
    return path
