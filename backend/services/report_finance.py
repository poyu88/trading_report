"""報表財務計算：價金拆分、收入／成本、未配對守恆欄。"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Protocol

TWOPLACES = Decimal("0.01")

PARTIAL_MATCH_NOTE = "費用全額落點；尚有未配對殘量；本列損益非完整原始交易損益"


class _HasGrossQty(Protocol):
    quantity: int
    gross_amount: Decimal
    commission: Decimal
    tax: Decimal
    interest: Decimal
    trade_id: str


class _HasAllocQty(Protocol):
    quantity: int
    sell_trade_id: str


def q2(value: Decimal) -> Decimal:
    return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def split_gross(total: Decimal, pieces: list[int]) -> list[Decimal]:
    """依股數拆價金，尾差歸最後片段，合計等於 total。"""
    if not pieces:
        return []
    total_qty = sum(pieces)
    if total_qty <= 0:
        return [Decimal(0)] * len(pieces)
    amounts: list[Decimal] = []
    allocated = Decimal(0)
    for i, qty in enumerate(pieces):
        if i == len(pieces) - 1:
            amounts.append(total - allocated)
        else:
            part = q2(total * Decimal(qty) / Decimal(total_qty))
            amounts.append(part)
            allocated += part
    return amounts


def split_sell_gross_with_residual(
    sell_qty: int,
    sell_gross: Decimal,
    matched_qtys: list[int],
) -> tuple[list[Decimal], Decimal | None, int]:
    """回傳 (已配對片段價金, 未配對殘量價金或 None, 未配對股數)。"""
    matched_total = sum(matched_qtys)
    unmatched_qty = sell_qty - matched_total
    if unmatched_qty < 0:
        raise ValueError("配對股數超過賣出股數")
    pieces = list(matched_qtys)
    if unmatched_qty > 0:
        pieces.append(unmatched_qty)
    parts = split_gross(sell_gross, pieces)
    if unmatched_qty > 0:
        return parts[:-1], parts[-1], unmatched_qty
    return parts, None, 0


def compute_income(
    sell_gross: Decimal,
    *,
    sell_commission: Decimal,
    sell_tax: Decimal,
    sell_interest: Decimal,
) -> Decimal:
    return q2(sell_gross - sell_commission - sell_tax - sell_interest)


def compute_cost(buy_gross: Decimal, buy_commission: Decimal) -> Decimal:
    return q2(buy_gross + buy_commission)


def enrich_sell_issue_finance(
    *,
    sell_trade: _HasGrossQty,
    allocations: list[_HasAllocQty],
    base_detail: dict[str, Any],
) -> dict[str, Any]:
    """為 INSUFFICIENT_PRIOR_BUYS 等例外補 matched/unmatched 價金守恆欄。"""
    matched_qtys = [a.quantity for a in allocations]
    matched_qty = sum(matched_qtys)
    unmatched_qty = int(base_detail.get("unmatched_quantity", sell_trade.quantity - matched_qty))
    matched_parts, unmatched_gross, computed_unmatched = split_sell_gross_with_residual(
        sell_trade.quantity,
        sell_trade.gross_amount,
        matched_qtys,
    )
    if computed_unmatched != unmatched_qty and matched_qty + unmatched_qty == sell_trade.quantity:
        pass  # 以 base_detail 為準時仍用拆分結果
    matched_gross = sum(matched_parts, Decimal(0)) if matched_parts else Decimal(0)
    if unmatched_gross is None:
        unmatched_gross = Decimal(0)
    detail = dict(base_detail)
    detail["matched_quantity"] = matched_qty
    detail["unmatched_quantity"] = unmatched_qty
    detail["matched_gross"] = str(matched_gross)
    detail["unmatched_gross"] = str(unmatched_gross)
    detail["source_gross"] = str(sell_trade.gross_amount)
    detail["fee_placement"] = (
        "賣出手續費／稅／利息落於主明細第一個已配對片段；"
        "未配對殘量不重複計費；完全無配對時費用僅見例外／配套明細說明"
        if matched_qty > 0
        else "此賣出完全未配對；費用未落入主明細 A～W，見配套未配對明細／資料庫原值"
    )
    return detail
