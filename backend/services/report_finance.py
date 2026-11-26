"""報表財務計算：價金拆分、收入／成本、未配對守恆欄。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Any, Protocol

TWOPLACES = Decimal("0.01")
AMOUNT_TOLERANCE = Decimal(1)
AMOUNT_CONSERVATION_OUT_OF_TOLERANCE = "AMOUNT_CONSERVATION_OUT_OF_TOLERANCE"

PARTIAL_MATCH_NOTE = "費用全額落點；尚有未配對殘量；本列損益非完整原始交易損益"


class _HasGrossQty(Protocol):
    quantity: int
    gross_amount: Decimal
    commission: Decimal
    tax: Decimal
    interest: Decimal
    trade_id: str
    unit_price: Decimal


class _HasAllocQty(Protocol):
    quantity: int
    sell_trade_id: str
    buy_trade_id: str | None


class _ConservationTrade(Protocol):
    """價金守恆檢查所需之交易欄位。"""

    side: str
    trade_id: str
    quantity: int
    gross_amount: Decimal
    unit_price: Decimal


class _ConservationAlloc(Protocol):
    """價金守恆檢查所需之配對片段欄位。"""

    quantity: int
    sell_trade_id: str
    buy_trade_id: str | None
    sequence_no: int


class _ConservationUnsold(Protocol):
    """價金守恆檢查所需之未售庫存欄位。"""

    buy_trade_id: str | None
    available: int


@dataclass(frozen=True)
class FragmentAmountAllocation:
    amounts: list[Decimal]
    truncated: list[Decimal]
    adjustments: list[Decimal]
    difference: Decimal
    calculated_total: Decimal
    final_total: Decimal
    out_of_tolerance: bool
    conservation_ok: bool
    adjustment_reason: str | None
    exception_code: str | None
    quantities: list[int]
    unit_price: Decimal
    original_gross: Decimal
    trade_id: str | None = None

    def exception_detail(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "original_gross": str(self.original_gross),
            "unit_price": str(self.unit_price),
            "quantities": list(self.quantities),
            "truncated_amounts": [str(x) for x in self.truncated],
            "final_amounts": [str(x) for x in self.amounts],
            "calculated_total": str(self.calculated_total),
            "difference": str(self.difference),
            "adjustments": [str(x) for x in self.adjustments],
            "adjustment_reason": self.adjustment_reason,
            "conservation_ok": self.conservation_ok,
            "out_of_tolerance": self.out_of_tolerance,
        }


def q2(value: Decimal) -> Decimal:
    """四捨五入至小數兩位（金額欄位）。

    Args:
        value: 任意精度金額。

    Returns:
        以 ROUND_HALF_UP 量化至 ``0.01`` 的 Decimal。
    """
    return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def trunc_toward_zero(value: Decimal) -> Decimal:
    """朝零截斷為整數 Decimal（TRUNC 價金片段；含負數）。

    Args:
        value: ``qty × unit_price`` 等乘積。

    Returns:
        朝零取整後的整數 Decimal（非四捨五入）。

    Note:
        ``decimal.ROUND_DOWN`` 語意為朝零；不得對負數使用 ``ROUND_UP``（離零）。
    """
    return value.to_integral_value(rounding=ROUND_DOWN)


def allocate_trade_fragment_amounts(
    unit_price: Decimal,
    gross: Decimal,
    qtys: list[int],
    *,
    tolerance: Decimal = AMOUNT_TOLERANCE,
    trade_id: str | None = None,
) -> FragmentAmountAllocation:
    """依 TRUNC(qty×unit_price) 分配片段價金；|diff|≤tolerance 才調最後片段。

    不變量：禁止比例／餘額法；僅在容許差內調整**最後**片段；
    ``|difference| > tolerance`` 時標記超限且不補差。

    Args:
        unit_price: 單價（與來源交易一致）。
        gross: 原始成交價金總額（須與各片段最終金額之和在容許差內守恆）。
        qtys: 各片段股數（非負整數；順序即報表片段順序）。
        tolerance: 容許絕對差，預設 ``AMOUNT_TOLERANCE``（1 元）。
        trade_id: 可選，寫入例外明細。

    Returns:
        ``FragmentAmountAllocation``（含截斷值、調整、守恆旗標）。
    """
    if not qtys:
        return FragmentAmountAllocation(
            amounts=[],
            truncated=[],
            adjustments=[],
            difference=Decimal(0),
            calculated_total=Decimal(0),
            final_total=Decimal(0),
            out_of_tolerance=False,
            conservation_ok=gross == 0,
            adjustment_reason=None,
            exception_code=None,
            quantities=[],
            unit_price=unit_price,
            original_gross=gross,
            trade_id=trade_id,
        )

    truncated = [trunc_toward_zero(Decimal(q) * unit_price) for q in qtys]
    calculated_total = sum(truncated, Decimal(0))
    difference = gross - calculated_total
    adjustments = [Decimal(0)] * len(qtys)
    amounts = list(truncated)
    adjustment_reason: str | None = None
    out_of_tolerance = False
    exception_code: str | None = None

    if difference == 0:
        pass
    elif abs(difference) <= tolerance:
        adjustments[-1] = difference
        amounts[-1] = amounts[-1] + difference
        adjustment_reason = f"容許差內調整最後片段 {difference}"
    else:
        out_of_tolerance = True
        exception_code = AMOUNT_CONSERVATION_OUT_OF_TOLERANCE
        adjustment_reason = f"超容許差 |{difference}| > {tolerance}；保留截斷結果不補差"

    final_total = sum(amounts, Decimal(0))
    conservation_ok = final_total == gross and not out_of_tolerance
    return FragmentAmountAllocation(
        amounts=amounts,
        truncated=truncated,
        adjustments=adjustments,
        difference=difference,
        calculated_total=calculated_total,
        final_total=final_total,
        out_of_tolerance=out_of_tolerance,
        conservation_ok=conservation_ok,
        adjustment_reason=adjustment_reason,
        exception_code=exception_code,
        quantities=list(qtys),
        unit_price=unit_price,
        original_gross=gross,
        trade_id=trade_id,
    )


def split_gross(total: Decimal, pieces: list[int]) -> list[Decimal]:
    """已廢止：不得再以比例／餘額法拆價金。請改用 allocate_trade_fragment_amounts。"""
    raise RuntimeError(
        "split_gross 已廢止（禁止比例／餘額法）；請使用 allocate_trade_fragment_amounts"
    )


def split_sell_gross_with_residual(
    sell_qty: int,
    sell_gross: Decimal,
    matched_qtys: list[int],
    *,
    unit_price: Decimal,
    trade_id: str | None = None,
) -> tuple[list[Decimal], Decimal | None, int, FragmentAmountAllocation]:
    """將賣出價金拆成已配對片段與未配對殘量。

    Args:
        sell_qty: 賣出總股數。
        sell_gross: 賣出原始價金。
        matched_qtys: 已配對各片段股數。
        unit_price: 賣出單價。
        trade_id: 可選，寫入例外明細。

    Returns:
        ``(已配對片段價金, 未配對殘量價金或 None, 未配對股數, 完整分配結果)``。

    Raises:
        ValueError: 配對股數超過賣出股數。
    """
    matched_total = sum(matched_qtys)
    unmatched_qty = sell_qty - matched_total
    if unmatched_qty < 0:
        raise ValueError("配對股數超過賣出股數")
    pieces = list(matched_qtys)
    if unmatched_qty > 0:
        pieces.append(unmatched_qty)
    alloc = allocate_trade_fragment_amounts(
        unit_price, sell_gross, pieces, trade_id=trade_id
    )
    if unmatched_qty > 0:
        return alloc.amounts[:-1], alloc.amounts[-1], unmatched_qty, alloc
    return alloc.amounts, None, 0, alloc


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
    matched_parts, unmatched_gross, computed_unmatched, alloc = split_sell_gross_with_residual(
        sell_trade.quantity,
        sell_trade.gross_amount,
        matched_qtys,
        unit_price=sell_trade.unit_price,
        trade_id=sell_trade.trade_id,
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
    detail["calculated_total"] = str(alloc.calculated_total)
    detail["difference"] = str(alloc.difference)
    detail["amount_conservation_ok"] = alloc.conservation_ok
    detail["fee_placement"] = (
        "賣出手續費／稅／利息落於主明細第一個已配對片段；"
        "未配對殘量不重複計費；完全無配對時費用僅見例外／配套明細說明"
        if matched_qty > 0
        else "此賣出完全未配對；費用未落入主明細 A～W，見配套未配對明細／資料庫原值"
    )
    return detail


def collect_amount_conservation_issues(
    trades: Sequence[_ConservationTrade],
    allocations: Sequence[_ConservationAlloc],
    unsold: Sequence[_ConservationUnsold],
) -> list[dict[str, Any]]:
    """逐筆檢查買／賣價金守恆；超限回傳 AMOUNT_CONSERVATION_OUT_OF_TOLERANCE。

    Args:
        trades: 具 side／trade_id／quantity／gross_amount／unit_price 的交易列（唯讀序列）。
        allocations: 具 sell／buy trade id、quantity、sequence_no 的配對列。
        unsold: 具 buy_trade_id／available 的未售庫存。

    Returns:
        超容許差之 issue 字典清單（含 ``detail`` 守恆欄）；通過則空清單。

    Note:
        參數使用 ``Sequence``（非 ``list``）以避免 Protocol 與具體 ``list[TradeView]``
        等型別在靜態檢查時因 list invariant 不相容；執行期僅迭代、不改寫輸入。
    """
    from collections import defaultdict

    sell_allocs: dict[str, list[_ConservationAlloc]] = defaultdict(list)
    buy_matched: dict[str, list[int]] = defaultdict(list)
    for a in allocations:
        sell_allocs[a.sell_trade_id].append(a)
        if a.buy_trade_id:
            buy_matched[a.buy_trade_id].append(a.quantity)

    unsold_by_buy: dict[str, int] = {}
    for lot in unsold:
        if lot.buy_trade_id:
            unsold_by_buy[lot.buy_trade_id] = unsold_by_buy.get(lot.buy_trade_id, 0) + lot.available

    issues: list[dict[str, Any]] = []
    for t in trades:
        if t.side == "SELL":
            alist = sorted(sell_allocs.get(t.trade_id, []), key=lambda x: x.sequence_no)
            _parts, _resid, _uq, alloc = split_sell_gross_with_residual(
                t.quantity,
                t.gross_amount,
                [a.quantity for a in alist],
                unit_price=t.unit_price,
                trade_id=t.trade_id,
            )
        else:
            qtys = list(buy_matched.get(t.trade_id, []))
            rem = unsold_by_buy.get(t.trade_id)
            if rem:
                qtys.append(rem)
            if not qtys and t.quantity > 0:
                qtys = [t.quantity]
            if sum(qtys) != t.quantity and qtys:
                # 若尚未投影完整殘量，仍以已知名片段檢查截斷
                pass
            if not qtys:
                continue
            alloc = allocate_trade_fragment_amounts(
                t.unit_price, t.gross_amount, qtys, trade_id=t.trade_id
            )
        if alloc.out_of_tolerance:
            issues.append(
                {
                    "id": f"amt-{t.trade_id}",
                    "code": AMOUNT_CONSERVATION_OUT_OF_TOLERANCE,
                    "severity": "warning",
                    "trade_id": t.trade_id,
                    "detail": alloc.exception_detail(),
                    "conservation_ok": False,
                }
            )
    return issues
