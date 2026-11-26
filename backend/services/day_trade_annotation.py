"""Independent Day-Trade Annotation（Layer 3）。

僅讀 trades／allocations 產出稽核註記；不得寫回配對或改寫財務結果。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal

from backend.domain.models import Allocation, Trade
from backend.services.fifo_matcher import MATCH_TYPE_SAME_DAY

TAX_RULES_VERSION = "tw_sec_tax_v1"

# 台股證交稅規則表（版本化；禁止呼叫端硬編碼）
_TAX_RULES: dict[str, Decimal] = {
    "STANDARD_RATE": Decimal("0.003"),
    "DAY_TRADE_HALF_RATE": Decimal("0.0015"),
}
_TAX_TOLERANCE = Decimal(1)  # 元；容許取整差異


@dataclass(frozen=True)
class DayTradeCandidate:
    account_id: str
    symbol: str
    trade_date: str
    currency: str
    buy_qty: int
    sell_qty: int
    suspected_support_qty: int
    tax_evidence: str
    annotation_status: str
    match_type_label: str


@dataclass
class DayTradeAnnotationResult:
    rules_version: str
    suspected_day_trade_qty: int
    same_day_reconciled_qty: int
    candidates: list[DayTradeCandidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _expected_tax(gross: Decimal, rate: Decimal) -> Decimal:
    return (gross * rate).quantize(Decimal(1))


def _sell_tax_evidence(sell: Trade) -> str:
    if sell.side != "SELL" or sell.gross_amount <= 0:
        return "INSUFFICIENT_EVIDENCE"
    half = _expected_tax(sell.gross_amount, _TAX_RULES["DAY_TRADE_HALF_RATE"])
    full = _expected_tax(sell.gross_amount, _TAX_RULES["STANDARD_RATE"])
    if abs(sell.tax - half) <= _TAX_TOLERANCE:
        return "HALF_RATE"
    if abs(sell.tax - full) <= _TAX_TOLERANCE:
        return "STANDARD_RATE"
    return "INSUFFICIENT_EVIDENCE"


def annotate_day_trades(
    trades: Iterable[Trade],
    allocations: Iterable[Allocation],
) -> DayTradeAnnotationResult:
    """依同日可支持買賣股數與稅證據產出現沖嫌疑註記。

    Args:
        trades: 領域成交（唯讀）。
        allocations: FIFO 配對結果（唯讀；僅用於統計 SAME_DAY_RECONCILED）。

    Returns:
        稽核附掛結構；失敗時以 warnings 表達，不拋錯改寫財務。
    """
    warnings: list[str] = []
    try:
        trade_list = list(trades)
        alloc_list = list(allocations)
    except Exception as exc:  # noqa: BLE001 — 註記層必須吞例外
        return DayTradeAnnotationResult(
            rules_version=TAX_RULES_VERSION,
            suspected_day_trade_qty=0,
            same_day_reconciled_qty=0,
            candidates=[],
            warnings=[f"ANNOTATION_FAILED:{type(exc).__name__}"],
        )

    same_day_reconciled_qty = sum(
        a.quantity for a in alloc_list if a.match_type == MATCH_TYPE_SAME_DAY
    )

    groups: dict[tuple[str, str, str, str], list[Trade]] = defaultdict(list)
    for t in trade_list:
        if t.trade_type != "CASH":
            continue
        key = (t.account_id, t.symbol, t.currency, t.trade_date.isoformat())
        groups[key].append(t)

    candidates: list[DayTradeCandidate] = []
    suspected_total = 0

    for (account_id, symbol, currency, day), group in sorted(groups.items()):
        buys = [t for t in group if t.side == "BUY"]
        sells = [t for t in group if t.side == "SELL"]
        if not buys or not sells:
            continue
        buy_qty = sum(t.quantity for t in buys)
        sell_qty = sum(t.quantity for t in sells)
        support = min(buy_qty, sell_qty)
        if support <= 0:
            continue

        evidence_flags = {_sell_tax_evidence(s) for s in sells}
        if "HALF_RATE" in evidence_flags:
            tax_evidence = "HALF_RATE"
            status = "SUSPECTED_DAY_TRADE"
        elif evidence_flags == {"STANDARD_RATE"}:
            tax_evidence = "STANDARD_RATE"
            status = "SAME_DAY_OVERLAP_ONLY"
        else:
            tax_evidence = "INSUFFICIENT_EVIDENCE"
            status = "INSUFFICIENT_EVIDENCE"

        # 手續費不得驅動判定（刻意不讀 commission）
        day_recon = sum(
            a.quantity
            for a in alloc_list
            if a.match_type == MATCH_TYPE_SAME_DAY
            and any(s.trade_id == a.sell_trade_id for s in sells)
        )
        match_label = MATCH_TYPE_SAME_DAY if day_recon > 0 else "NONE"

        candidates.append(
            DayTradeCandidate(
                account_id=account_id,
                symbol=symbol,
                trade_date=day,
                currency=currency,
                buy_qty=buy_qty,
                sell_qty=sell_qty,
                suspected_support_qty=support if tax_evidence == "HALF_RATE" else 0,
                tax_evidence=tax_evidence,
                annotation_status=status,
                match_type_label=match_label,
            )
        )
        if tax_evidence == "HALF_RATE":
            suspected_total += support

    return DayTradeAnnotationResult(
        rules_version=TAX_RULES_VERSION,
        suspected_day_trade_qty=suspected_total,
        same_day_reconciled_qty=same_day_reconciled_qty,
        candidates=candidates,
        warnings=warnings,
    )


def annotation_to_audit_dict(result: DayTradeAnnotationResult) -> dict:
    """將註記轉為 audit.json 增量欄位。"""
    return {
        "day_trade_annotation": {
            "rules_version": result.rules_version,
            "suspected_day_trade_qty": result.suspected_day_trade_qty,
            "same_day_reconciled_qty": result.same_day_reconciled_qty,
            "candidates": [
                {
                    "account_id": c.account_id,
                    "symbol": c.symbol,
                    "trade_date": c.trade_date,
                    "currency": c.currency,
                    "buy_qty": c.buy_qty,
                    "sell_qty": c.sell_qty,
                    "suspected_support_qty": c.suspected_support_qty,
                    "tax_evidence": c.tax_evidence,
                    "annotation_status": c.annotation_status,
                    "match_type_label": c.match_type_label,
                }
                for c in result.candidates
            ],
            "warnings": list(result.warnings),
        }
    }
