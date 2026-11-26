"""Independent Day-Trade Annotation（Layer 3）。

僅讀 trades／allocations 產出稽核註記；不得寫回配對或改寫財務結果。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from backend.domain.models import Allocation, Trade
from backend.services.fifo_matcher import MATCH_TYPE_SAME_DAY

TAX_RULES_VERSION = "tw_sec_tax_v2"

# 台股證交稅規則表（版本化；禁止呼叫端硬編碼）
# 來源：證交稅條例一般股票稅率；現股當沖半稅自 2017-04-28 起適用於一般股票。
# 本層為最小可驗證適用範圍，非完整稅務引擎；ETF／未知商品／生效日前 → INSUFFICIENT。
_TAX_RULES: dict[str, Decimal] = {
    "STANDARD_RATE": Decimal("0.003"),
    "DAY_TRADE_HALF_RATE": Decimal("0.0015"),
}
_TAX_TOLERANCE = Decimal(1)  # 元；容許取整差異
_HALF_RATE_EFFECTIVE_FROM = date(2017, 4, 28)
_ELIGIBLE_INSTRUMENT_CLASSES = frozenset({"TW_COMMON_STOCK"})
_TAX_RULE_SOURCE = (
    "TWSE/TPEx securities transaction tax; day-trade half-rate for common stock "
    f"effective {_HALF_RATE_EFFECTIVE_FROM.isoformat()}"
)


@dataclass(frozen=True)
class DayTradeCandidate:
    """單一日／帳戶／標的之現沖嫌疑候選。

    Attributes:
        suspected_support_qty: ``min(buy_qty, half_rate_sell_qty)``；非 HALF 證據時為 0。
        half_rate_sell_qty: 組內稅證據為 HALF_RATE 的賣出股數合計。
        reconciled_quantity: 該組賣出對應之 ``SAME_DAY_RECONCILED`` 配對股數。
        uncertainty_reason: 無法標 SUSPECTED 時的可追溯原因；否則空字串。
        same_day_sell_trade_ids: 同日全部 SELL trade_id。
        half_rate_sell_trade_ids: 僅 HALF_RATE 證據之 SELL trade_id。
        candidate_sell_trade_ids: 與 ``half_rate_sell_trade_ids`` 同義（候選賣出）。
        sell_tax_evidences: 逐筆賣出稅證據（含 source_row_id）。
    """

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
    candidate_sell_trade_ids: tuple[str, ...] = ()
    same_day_sell_trade_ids: tuple[str, ...] = ()
    half_rate_sell_trade_ids: tuple[str, ...] = ()
    source_buy_trade_ids: tuple[str, ...] = ()
    source_row_ids: tuple[str, ...] = ()
    sell_tax_evidences: tuple[dict, ...] = ()
    half_rate_sell_qty: int = 0
    reconciled_quantity: int = 0
    uncertainty_reason: str = ""
    tax_rule_version: str = TAX_RULES_VERSION


@dataclass
class DayTradeAnnotationResult:
    """Annotation 彙總結果（稽核附掛；不改寫財務）。"""

    rules_version: str
    suspected_day_trade_qty: int
    same_day_reconciled_qty: int
    candidates: list[DayTradeCandidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _expected_tax(gross: Decimal, rate: Decimal) -> Decimal:
    """依規則表計算期望證交稅（元；``ROUND_HALF_UP``）。"""
    return (gross * rate).quantize(Decimal(1), rounding=ROUND_HALF_UP)


def _classify_instrument(symbol: str, name: str | None) -> str:
    """最小商品分類（可驗證；非完整商品主檔）。

    Returns:
        ``TW_COMMON_STOCK``｜``TW_ETF``｜``UNKNOWN``。
    """
    s = (symbol or "").strip().upper()
    n = (name or "").upper()
    if "ETF" in n:
        return "TW_ETF"
    if len(s) == 4 and s.isdigit():
        if s.startswith("00"):
            return "TW_ETF"
        return "TW_COMMON_STOCK"
    return "UNKNOWN"


def _sell_tax_evidence(sell: Trade) -> str:
    """對單一賣出判定稅證據。

    適用條件（全部滿足才比對規則表）：
    - ``currency=TWD``、``trade_type=CASH``、``gross_amount > 0``
    - 商品分類 ∈ ``TW_COMMON_STOCK``
    - 交易日 ≥ 減半稅生效日才可比對 HALF_RATE；否則僅能比對 STANDARD_RATE

    若同時落入半稅與全稅容差 → ``AMBIGUOUS_TAX_EVIDENCE``（優先於 HALF_RATE）。
    """
    if sell.side != "SELL":
        return "INSUFFICIENT_EVIDENCE"
    if sell.currency != "TWD" or sell.trade_type != "CASH":
        return "INSUFFICIENT_EVIDENCE"
    if sell.gross_amount <= 0:
        return "INSUFFICIENT_EVIDENCE"

    instrument = _classify_instrument(sell.symbol, sell.name)
    if instrument not in _ELIGIBLE_INSTRUMENT_CLASSES:
        return "INSUFFICIENT_EVIDENCE"

    full = _expected_tax(sell.gross_amount, _TAX_RULES["STANDARD_RATE"])
    near_full = abs(sell.tax - full) <= _TAX_TOLERANCE

    half_applicable = sell.trade_date >= _HALF_RATE_EFFECTIVE_FROM
    if half_applicable:
        half = _expected_tax(sell.gross_amount, _TAX_RULES["DAY_TRADE_HALF_RATE"])
        near_half = abs(sell.tax - half) <= _TAX_TOLERANCE
        if near_half and near_full:
            return "AMBIGUOUS_TAX_EVIDENCE"
        if near_half:
            return "HALF_RATE"
        if near_full:
            return "STANDARD_RATE"
        return "INSUFFICIENT_EVIDENCE"

    # 生效日前：不得推論 HALF_RATE
    if near_full:
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
        稽核附掛結構；失敗時以 ``warnings=["ANNOTATION_FAILED:..."]`` 表達，不拋錯。

    Side Effects:
        無。不寫 DB、不改傳入物件之財務欄位。

    Financial invariants:
        Annotation ON／OFF 不得改變 allocations、未售、blocking、價金／費／稅。
        ``suspected_support_qty = min(buy_qty, half_rate_sell_qty)``；
        組含 ``AMBIGUOUS_TAX_EVIDENCE`` 時不得標 ``SUSPECTED_DAY_TRADE``。
    """
    try:
        return _annotate_day_trades_impl(trades, allocations)
    except Exception as exc:  # noqa: BLE001 — 註記層必須吞例外
        return DayTradeAnnotationResult(
            rules_version=TAX_RULES_VERSION,
            suspected_day_trade_qty=0,
            same_day_reconciled_qty=0,
            candidates=[],
            warnings=[f"ANNOTATION_FAILED:{type(exc).__name__}"],
        )


def _annotate_day_trades_impl(
    trades: Iterable[Trade],
    allocations: Iterable[Allocation],
) -> DayTradeAnnotationResult:
    trade_list = list(trades)
    alloc_list = list(allocations)
    warnings: list[str] = []

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
        if min(buy_qty, sell_qty) <= 0:
            continue

        sell_evidence = [(s, _sell_tax_evidence(s)) for s in sells]
        evidence_flags = {ev for _, ev in sell_evidence}
        half_rate_sells = [s for s, ev in sell_evidence if ev == "HALF_RATE"]
        half_rate_sell_qty = sum(s.quantity for s in half_rate_sells)

        day_recon = sum(
            a.quantity
            for a in alloc_list
            if a.match_type == MATCH_TYPE_SAME_DAY
            and any(s.trade_id == a.sell_trade_id for s in sells)
        )
        match_label = MATCH_TYPE_SAME_DAY if day_recon > 0 else "NONE"

        uncertainty = ""
        if "AMBIGUOUS_TAX_EVIDENCE" in evidence_flags:
            tax_evidence = "AMBIGUOUS_TAX_EVIDENCE"
            status = "AMBIGUOUS_TAX_EVIDENCE"
            support = 0
            uncertainty = "tax_matches_both_half_and_full_within_tolerance"
        elif "HALF_RATE" in evidence_flags:
            tax_evidence = "HALF_RATE"
            status = "SUSPECTED_DAY_TRADE"
            support = min(buy_qty, half_rate_sell_qty)
        elif evidence_flags == {"STANDARD_RATE"}:
            tax_evidence = "STANDARD_RATE"
            status = "SAME_DAY_OVERLAP_ONLY"
            support = 0
            uncertainty = "standard_rate_only"
        else:
            tax_evidence = "INSUFFICIENT_EVIDENCE"
            status = "INSUFFICIENT_EVIDENCE"
            support = 0
            uncertainty = "tax_rule_not_applicable_or_unmatched"

        same_day_ids = tuple(sorted(s.trade_id for s in sells))
        half_ids = tuple(sorted(s.trade_id for s in half_rate_sells))
        source_rows = tuple(
            sorted({t.source_row_id for t in buys + sells if t.source_row_id})
        )
        sell_ev_payload = tuple(
            {
                "trade_id": s.trade_id,
                "tax_evidence": ev,
                "quantity": s.quantity,
                "source_row_id": s.source_row_id,
                "instrument_class": _classify_instrument(s.symbol, s.name),
            }
            for s, ev in sorted(sell_evidence, key=lambda x: x[0].trade_id)
        )

        # 手續費不得驅動判定（刻意不讀 commission）
        candidates.append(
            DayTradeCandidate(
                account_id=account_id,
                symbol=symbol,
                trade_date=day,
                currency=currency,
                buy_qty=buy_qty,
                sell_qty=sell_qty,
                suspected_support_qty=support,
                tax_evidence=tax_evidence,
                annotation_status=status,
                match_type_label=match_label,
                candidate_sell_trade_ids=half_ids,
                same_day_sell_trade_ids=same_day_ids,
                half_rate_sell_trade_ids=half_ids,
                source_buy_trade_ids=tuple(sorted(b.trade_id for b in buys)),
                source_row_ids=source_rows,
                sell_tax_evidences=sell_ev_payload,
                half_rate_sell_qty=half_rate_sell_qty,
                reconciled_quantity=day_recon,
                uncertainty_reason=uncertainty,
                tax_rule_version=TAX_RULES_VERSION,
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
    """將註記轉為 audit.json 增量欄位。

    Args:
        result: ``annotate_day_trades`` 產出。

    Returns:
        含 ``day_trade_annotation`` 鍵之 dict；候選含 CR-12 可追溯欄位。

    Side Effects:
        無。
    """
    failed = any(w.startswith("ANNOTATION_FAILED:") for w in result.warnings)
    return {
        "day_trade_annotation": {
            "rules_version": result.rules_version,
            "status": "FAILED" if failed else "OK",
            "tax_rule_source": _TAX_RULE_SOURCE,
            "half_rate_effective_from": _HALF_RATE_EFFECTIVE_FROM.isoformat(),
            "eligible_instrument_classes": sorted(_ELIGIBLE_INSTRUMENT_CLASSES),
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
                    "candidate_sell_trade_ids": list(c.candidate_sell_trade_ids),
                    "same_day_sell_trade_ids": list(c.same_day_sell_trade_ids),
                    "half_rate_sell_trade_ids": list(c.half_rate_sell_trade_ids),
                    "source_buy_trade_ids": list(c.source_buy_trade_ids),
                    "source_row_ids": list(c.source_row_ids),
                    "sell_tax_evidences": [dict(e) for e in c.sell_tax_evidences],
                    "half_rate_sell_qty": c.half_rate_sell_qty,
                    "reconciled_quantity": c.reconciled_quantity,
                    "uncertainty_reason": c.uncertainty_reason,
                    "tax_rule_version": c.tax_rule_version,
                }
                for c in result.candidates
            ],
            "warnings": list(result.warnings),
        }
    }
