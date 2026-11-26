"""Independent Day-Trade Annotation（Layer 3）。

僅讀 trades／allocations 產出稽核註記；不得寫回配對或改寫財務結果。
啟發式商品分類 ≠ 商品主檔驗證；本層不影響 Matching Engine。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from backend.domain.models import Allocation, Trade
from backend.services.fifo_matcher import MATCH_TYPE_SAME_DAY

TAX_RULES_VERSION = "tw_sec_tax_v3"

# 台股證交稅規則表（版本化；禁止呼叫端硬編碼）
# 官方來源（核實日 2026-11-26；輔助分析用，非完整稅務引擎）：
# - 證券交易稅條例一般股票稅率 0.3%
# - 現股當沖減半（0.15%）自 2017-04-28 起適用於一般股票（非 ETF／特殊商品）
# 取整／容差：ROUND_HALF_UP＋1 元為**輔助分析假設**（券商列印／取整差異），
#   非法定取整條文之完整引用；不得視為已確認官方計算規範。
# `_TAX_RULES_VALID_THROUGH`＝本版規則表**程式保守核實期限**（非法令日落日）；
#   次日／未來未知規則 → INSUFFICIENT_EVIDENCE。
# 四碼啟發式僅推論 INFERRED_TW_COMMON_STOCK，不得宣稱已確認普通股。
_TAX_RULES: dict[str, Decimal] = {
    "STANDARD_RATE": Decimal("0.003"),
    "DAY_TRADE_HALF_RATE": Decimal("0.0015"),
}
_TAX_TOLERANCE = Decimal(1)  # 元；輔助分析假設
_TAX_ROUNDING = "ROUND_HALF_UP"
_TAX_ROUNDING_BASIS = "auxiliary_analysis_assumption"
_TAX_TOLERANCE_BASIS = "auxiliary_broker_print_rounding_assumption"
_HALF_RATE_EFFECTIVE_FROM = date(2017, 4, 28)
# 程式保守核實期限（含當日）；≠ 法定期限／政策日落日
_TAX_RULES_VALID_THROUGH = date(2026, 12, 31)
_TAX_RULES_SOURCE_VERIFIED_ON = date(2026, 11, 26)
_ELIGIBLE_INSTRUMENT_CLASSES = frozenset({"INFERRED_TW_COMMON_STOCK"})
_TAX_RULE_SOURCE = (
    "TW Securities Transaction Tax Act (common-stock 0.3%); "
    "day-trade half-rate 0.15% for eligible common stock "
    f"from {_HALF_RATE_EFFECTIVE_FROM.isoformat()}; "
    f"rule-table program verified through {_TAX_RULES_VALID_THROUGH.isoformat()} "
    f"(verified_on={_TAX_RULES_SOURCE_VERIFIED_ON.isoformat()}; "
    "inferred instrument class only; not a statutory sunset)"
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
        instrument_class: 啟發式推論類別（非商品主檔驗證結果）。
        classification_basis: ``symbol_heuristic_4digit``｜``name_keyword``｜``unknown``。
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
    instrument_class: str = "UNKNOWN"
    classification_basis: str = "unknown"


@dataclass
class DayTradeAnnotationResult:
    """Annotation 彙總結果（稽核附掛；不改寫財務）。"""

    rules_version: str
    suspected_day_trade_qty: int
    same_day_reconciled_qty: int
    candidates: list[DayTradeCandidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _expected_tax(gross: Decimal, rate: Decimal) -> Decimal:
    """依規則表計算期望證交稅（元；``ROUND_HALF_UP``）。

    Args:
        gross: 成交金額。
        rate: 稅率（規則表常數）。

    Returns:
        取整至元之期望稅額。
    """
    return (gross * rate).quantize(Decimal(1), rounding=ROUND_HALF_UP)


def _classify_instrument(symbol: str, name: str | None) -> tuple[str, str]:
    """最小商品分類（啟發式推論；非完整商品主檔驗證）。

    Args:
        symbol: 股票代號。
        name: 商品名稱（可為 None）。

    Returns:
        ``(instrument_class, classification_basis)``：
        - ``INFERRED_TW_COMMON_STOCK`` + ``symbol_heuristic_4digit``
        - ``TW_ETF`` + ``name_keyword`` 或 ``symbol_heuristic_4digit``
        - ``UNKNOWN`` + ``unknown``

    Note:
        啟發式 ≠ 已確認普通股；僅供稅證據適用範圍保守過濾，不影響 Matching Engine。
    """
    s = (symbol or "").strip().upper()
    n = (name or "").upper()
    if "ETF" in n:
        return "TW_ETF", "name_keyword"
    if len(s) == 4 and s.isdigit():
        if s.startswith("00"):
            return "TW_ETF", "symbol_heuristic_4digit"
        return "INFERRED_TW_COMMON_STOCK", "symbol_heuristic_4digit"
    return "UNKNOWN", "unknown"


def _sell_tax_evidence(sell: Trade) -> str:
    """對單一賣出判定稅證據。

    Args:
        sell: 賣出成交（唯讀）。

    Returns:
        ``HALF_RATE``｜``STANDARD_RATE``｜``AMBIGUOUS_TAX_EVIDENCE``｜
        ``INSUFFICIENT_EVIDENCE``。

    Tax applicability（期間須分開理解）:
        - ``currency=TWD``、``trade_type=CASH``、``gross_amount > 0``
        - 商品分類 ∈ ``INFERRED_TW_COMMON_STOCK``（啟發式；非主檔驗證）
        - ``trade_date > _TAX_RULES_VALID_THROUGH``（程式核實期限次日／未來）
          → 一律 ``INSUFFICIENT_EVIDENCE``（未知未來規則）
        - **一般稅（STANDARD_RATE）**：核實期限內、且分類適用時可比對
        - **減半稅（HALF_RATE）**：另須 ``trade_date >= _HALF_RATE_EFFECTIVE_FROM``
        - 減半生效日前：僅可比對 STANDARD_RATE，不得推論 HALF_RATE

    Uncertainty:
        若同時落入半稅與全稅容差 → ``AMBIGUOUS_TAX_EVIDENCE``（優先於 HALF_RATE）。
        取整／容差為輔助分析假設（見 ``_TAX_ROUNDING_BASIS``）。
    """
    if sell.side != "SELL":
        return "INSUFFICIENT_EVIDENCE"
    if sell.currency != "TWD" or sell.trade_type != "CASH":
        return "INSUFFICIENT_EVIDENCE"
    if sell.gross_amount <= 0:
        return "INSUFFICIENT_EVIDENCE"
    # 程式核實期限外（含未來未知規則）不得套用本版稅表
    if sell.trade_date > _TAX_RULES_VALID_THROUGH:
        return "INSUFFICIENT_EVIDENCE"

    instrument, _basis = _classify_instrument(sell.symbol, sell.name)
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

    # 減半生效日前：僅一般稅可比對；不得推論 HALF_RATE
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
    """實作 annotation 分組與稅證據彙總（僅由 ``annotate_day_trades`` 呼叫）。

    Args:
        trades: 領域成交（唯讀）。
        allocations: FIFO 配對結果（唯讀）。

    Returns:
        完整 ``DayTradeAnnotationResult``（可能含零候選）。

    Side Effects:
        無。

    Tax applicability / uncertainty:
        見 ``_sell_tax_evidence``；組級 AMBIGUOUS 優先於 HALF_RATE。
    """
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

        # 組級分類：彙總全部賣出證據；衝突時標 MIXED，不得任取 sells[0]
        class_pairs = [_classify_instrument(s.symbol, s.name) for s in sells]
        distinct_classes = {c for c, _ in class_pairs}
        if len(distinct_classes) > 1:
            instrument_class = "MIXED_INSTRUMENT_EVIDENCE"
            classification_basis = "conflicting_sell_evidence"
        else:
            instrument_class, classification_basis = class_pairs[0]

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
        if instrument_class == "MIXED_INSTRUMENT_EVIDENCE":
            tax_evidence = "INSUFFICIENT_EVIDENCE"
            status = "INSUFFICIENT_EVIDENCE"
            support = 0
            uncertainty = "instrument_classification_conflict"
        elif "AMBIGUOUS_TAX_EVIDENCE" in evidence_flags:
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
        sell_ev_items: list[dict] = []
        for s, ev in sorted(sell_evidence, key=lambda x: x[0].trade_id):
            iclass, ibasis = _classify_instrument(s.symbol, s.name)
            sell_ev_items.append(
                {
                    "trade_id": s.trade_id,
                    "tax_evidence": ev,
                    "quantity": s.quantity,
                    "source_row_id": s.source_row_id,
                    "instrument_class": iclass,
                    "classification_basis": ibasis,
                }
            )
        sell_ev_payload = tuple(sell_ev_items)

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
                instrument_class=instrument_class,
                classification_basis=classification_basis,
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
        含 ``day_trade_annotation`` 鍵之 dict；候選含 CR-12 可追溯欄位與
        CR-02 ``instrument_class``／``classification_basis``／有效窗／取整依據。

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
            "tax_rules_valid_through": _TAX_RULES_VALID_THROUGH.isoformat(),
            "tax_rules_valid_through_meaning": "program_verified_through_not_statutory_sunset",
            "tax_rules_source_verified_on": _TAX_RULES_SOURCE_VERIFIED_ON.isoformat(),
            "tax_rounding": _TAX_ROUNDING,
            "tax_rounding_basis": _TAX_ROUNDING_BASIS,
            "tax_tolerance_twd": int(_TAX_TOLERANCE),
            "tax_tolerance_basis": _TAX_TOLERANCE_BASIS,
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
                    "instrument_class": c.instrument_class,
                    "classification_basis": c.classification_basis,
                }
                for c in result.candidates
            ],
            "warnings": list(result.warnings),
        }
    }
