"""原始交易 ↔ 片段股數／價金／費用守恆核對表（含 TRUNC A～F 層級）。"""

from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from backend.reports.detail_projector import AllocationView, FifoTraceRow, TradeView
from backend.reports.detail_writer import unique_output_path
from backend.services.report_finance import (
    allocate_trade_fragment_amounts,
    split_sell_gross_with_residual,
)


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

    buy_matched: dict[str, list[int]] = {}
    for a in allocations:
        if a.buy_trade_id:
            buy_matched.setdefault(a.buy_trade_id, []).append(a.quantity)

    fieldnames = [
        "trade_id",
        "side",
        "symbol",
        "trade_date",
        "source_qty",
        "matched_qty",
        "unmatched_or_unsold_qty",
        "A_original_gross",
        "B_qty_x_price_sum",
        "C_truncated_total",
        "D_difference",
        "D_adjustment",
        "E_final_total",
        "F_conservation_ok",
        "out_of_tolerance",
        "adjustment_reason",
        "matched_gross",
        "residual_gross",
        "commission",
        "tax",
        "interest",
        # 相容舊欄名
        "source_gross",
        "gross_ok",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for t in sorted(trades, key=lambda x: (x.symbol, x.trade_date, x.trade_id)):
            if t.side == "SELL":
                alist = sorted(sell_allocs.get(t.trade_id, []), key=lambda a: a.sequence_no)
                matched_parts, unmatched_gross, unmatched_qty, alloc = split_sell_gross_with_residual(
                    t.quantity,
                    t.gross_amount,
                    [a.quantity for a in alist],
                    unit_price=t.unit_price,
                    trade_id=t.trade_id,
                )
                matched_qty = sum(a.quantity for a in alist)
                matched_gross = sum(matched_parts, Decimal(0))
                residual = unmatched_gross or Decimal(0)
                qty_x_price = sum(
                    (Decimal(q) * t.unit_price for q in alloc.quantities),
                    Decimal(0),
                )
                adj_sum = sum(alloc.adjustments, Decimal(0))
                writer.writerow(
                    {
                        "trade_id": t.trade_id,
                        "side": t.side,
                        "symbol": t.symbol,
                        "trade_date": t.trade_date.isoformat(),
                        "source_qty": t.quantity,
                        "matched_qty": matched_qty,
                        "unmatched_or_unsold_qty": unmatched_qty,
                        "A_original_gross": str(t.gross_amount),
                        "B_qty_x_price_sum": str(qty_x_price),
                        "C_truncated_total": str(alloc.calculated_total),
                        "D_difference": str(alloc.difference),
                        "D_adjustment": str(adj_sum),
                        "E_final_total": str(alloc.final_total),
                        "F_conservation_ok": str(alloc.conservation_ok),
                        "out_of_tolerance": str(alloc.out_of_tolerance),
                        "adjustment_reason": alloc.adjustment_reason or "",
                        "matched_gross": str(matched_gross),
                        "residual_gross": str(residual),
                        "commission": str(t.commission),
                        "tax": str(t.tax),
                        "interest": str(t.interest),
                        "source_gross": str(t.gross_amount),
                        "gross_ok": str(alloc.conservation_ok),
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
                # 依 FIFO：已配對（allocation 順序）＋未售
                qtys = list(buy_matched.get(t.trade_id, []))
                if unsold_qty > 0:
                    qtys.append(unsold_qty)
                if not qtys:
                    qtys = [t.quantity] if t.quantity else []
                alloc = allocate_trade_fragment_amounts(
                    t.unit_price, t.gross_amount, qtys, trade_id=t.trade_id
                )
                frag_gross = sum((r.gross_amount or Decimal(0) for r in buy_frags), Decimal(0))
                qty_x_price = sum((Decimal(q) * t.unit_price for q in qtys), Decimal(0))
                adj_sum = sum(alloc.adjustments, Decimal(0))
                writer.writerow(
                    {
                        "trade_id": t.trade_id,
                        "side": t.side,
                        "symbol": t.symbol,
                        "trade_date": t.trade_date.isoformat(),
                        "source_qty": t.quantity,
                        "matched_qty": sold,
                        "unmatched_or_unsold_qty": unsold_qty,
                        "A_original_gross": str(t.gross_amount),
                        "B_qty_x_price_sum": str(qty_x_price),
                        "C_truncated_total": str(alloc.calculated_total),
                        "D_difference": str(alloc.difference),
                        "D_adjustment": str(adj_sum),
                        "E_final_total": str(alloc.final_total),
                        "F_conservation_ok": str(alloc.conservation_ok),
                        "out_of_tolerance": str(alloc.out_of_tolerance),
                        "adjustment_reason": alloc.adjustment_reason or "",
                        "matched_gross": str(frag_gross),
                        "residual_gross": "",
                        "commission": str(t.commission),
                        "tax": str(t.tax),
                        "interest": str(t.interest),
                        "source_gross": str(t.gross_amount),
                        "gross_ok": str(alloc.conservation_ok and frag_gross == t.gross_amount),
                    }
                )
    return path
