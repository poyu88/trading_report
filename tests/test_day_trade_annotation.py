"""Independent Day-Trade Annotation（Layer 3）RED／回歸。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.domain.models import Allocation, Trade
from backend.services.day_trade_annotation import (
    TAX_RULES_VERSION,
    annotate_day_trades,
    annotation_to_audit_dict,
)
from backend.services.fifo_matcher import MatchInputTrade, run_fifo


def _trade(
    tid: str,
    day: str,
    side: str,
    qty: int,
    price: str,
    *,
    tax: str,
    commission: str = "20",
    symbol: str = "2236",
    name: str | None = None,
    account: str = "acc1",
    currency: str = "TWD",
    trade_type: str = "CASH",
    gross_amount: str | None = None,
) -> Trade:
    unit = Decimal(price)
    gross = Decimal(gross_amount) if gross_amount is not None else unit * qty
    tax_d = Decimal(tax)
    comm = Decimal(commission)
    net = gross - comm - tax_d if side == "SELL" else -(gross + comm)
    return Trade(
        trade_id=tid,
        account_id=account,
        source_row_id=f"src-{tid}",
        symbol=symbol,
        name=name,
        trade_date=date.fromisoformat(day),
        trade_time=None,
        trade_sequence=None,
        side=side,  # type: ignore[arg-type]
        trade_type=trade_type,  # type: ignore[arg-type]
        currency=currency,
        quantity=qty,
        unit_price=unit,
        gross_amount=gross,
        commission=comm,
        tax=tax_d,
        interest=Decimal(0),
        net_settlement=net,
    )


def _mit(t: Trade, source_order: int = 0) -> MatchInputTrade:
    return MatchInputTrade(
        trade_id=t.trade_id,
        account_id=t.account_id,
        symbol=t.symbol,
        trade_date=t.trade_date,
        trade_time=None,
        trade_sequence=None,
        side=t.side,
        trade_type=t.trade_type,
        currency=t.currency,
        quantity=t.quantity,
        unit_price=t.unit_price,
        source_order=source_order,
    )


def test_annotation_suspects_half_tax_same_day_support() -> None:
    """同日買賣＋賣出稅近減半 → suspected support；與 reconciled 分欄。"""
    # 賣 1000 @100 → gross 100000；一般稅 0.3%=300；減半 0.15%=150
    buy = _trade("b1", "2024-08-28", "BUY", 1000, "100", tax="0")
    sell_half = _trade("s1", "2024-08-28", "SELL", 1000, "100", tax="150")
    sell_full = _trade("s2", "2024-08-28", "SELL", 1000, "100", tax="300")
    trades = [buy, sell_half, sell_full]

    match = run_fifo("ann1", [_mit(buy, 1), _mit(sell_half, 2), _mit(sell_full, 3)])
    result = annotate_day_trades(trades, match.allocations)

    assert result.rules_version == TAX_RULES_VERSION
    # CR-01：僅半稅賣出股數計入 support（非整組 sell_qty）
    assert result.suspected_day_trade_qty == 1000
    assert result.same_day_reconciled_qty == sum(
        a.quantity for a in match.allocations if a.match_type == "SAME_DAY_RECONCILED"
    )
    assert hasattr(result, "suspected_day_trade_qty")
    assert hasattr(result, "same_day_reconciled_qty")
    assert any(c.tax_evidence == "HALF_RATE" for c in result.candidates)
    assert all(c.match_type_label != c.annotation_status for c in result.candidates)


def test_cr01_support_qty_uses_half_rate_sell_only() -> None:
    """CR-01：混合 HALF 100 + STANDARD 1900 → suspected = min(buy, half_rate_sell)=100。"""
    buy = _trade("b1", "2025-04-01", "BUY", 2000, "100", tax="0")
    sell_half = _trade("s_half", "2025-04-01", "SELL", 100, "100", tax="15")  # 10000*0.0015
    sell_full = _trade("s_full", "2025-04-01", "SELL", 1900, "100", tax="570")  # 190000*0.003
    result = annotate_day_trades([buy, sell_half, sell_full], allocations=[])

    assert len(result.candidates) == 1
    cand = result.candidates[0]
    assert cand.half_rate_sell_qty == 100
    assert cand.suspected_support_qty == 100
    assert result.suspected_day_trade_qty == 100
    assert cand.tax_evidence == "HALF_RATE"
    assert cand.annotation_status == "SUSPECTED_DAY_TRADE"


def test_cr01_buy_less_than_half_rate_sell_caps_support() -> None:
    """CR-01：買少於半稅賣 → support = buy_qty。"""
    buy = _trade("b1", "2025-04-02", "BUY", 50, "100", tax="0")
    sell_half = _trade("s1", "2025-04-02", "SELL", 100, "100", tax="15")
    result = annotate_day_trades([buy, sell_half], allocations=[])

    assert result.candidates[0].suspected_support_qty == 50
    assert result.suspected_day_trade_qty == 50


def test_cr01_no_same_day_buy_no_candidate() -> None:
    """CR-01：無同日買 → 不產 candidate。"""
    sell_half = _trade("s1", "2025-04-03", "SELL", 100, "100", tax="15")
    result = annotate_day_trades([sell_half], allocations=[])
    assert result.candidates == []
    assert result.suspected_day_trade_qty == 0


def test_cr02_non_twd_insufficient_evidence() -> None:
    """CR-02：非 TWD 不得硬套 0.3%/0.15% → INSUFFICIENT_EVIDENCE。"""
    buy = _trade("b1", "2025-04-04", "BUY", 1000, "100", tax="0", currency="USD")
    # gross=100000；若誤套台股減半 → tax 150 會被舊邏輯判 HALF_RATE
    sell = _trade("s1", "2025-04-04", "SELL", 1000, "100", tax="150", currency="USD")
    result = annotate_day_trades([buy, sell], allocations=[])

    assert len(result.candidates) == 1
    assert result.candidates[0].tax_evidence == "INSUFFICIENT_EVIDENCE"
    assert result.candidates[0].annotation_status == "INSUFFICIENT_EVIDENCE"
    assert result.candidates[0].suspected_support_qty == 0
    assert result.suspected_day_trade_qty == 0


def test_cr02_invalid_gross_insufficient_evidence() -> None:
    """CR-02：無效 gross_amount → INSUFFICIENT_EVIDENCE。"""
    buy = _trade("b1", "2025-04-05", "BUY", 100, "100", tax="0")
    sell = _trade(
        "s1",
        "2025-04-05",
        "SELL",
        100,
        "100",
        tax="15",
        gross_amount="0",
    )
    result = annotate_day_trades([buy, sell], allocations=[])
    assert result.candidates[0].tax_evidence == "INSUFFICIENT_EVIDENCE"
    assert result.suspected_day_trade_qty == 0


def test_cr02_eligible_common_stock_half_rate() -> None:
    """CR-02：四碼啟發式推論一般股票可判 HALF_RATE（非已驗證普通股）。"""
    buy = _trade("b1", "2025-04-10", "BUY", 1000, "100", tax="0", symbol="2330")
    sell = _trade("s1", "2025-04-10", "SELL", 1000, "100", tax="150", symbol="2330")
    result = annotate_day_trades([buy, sell], allocations=[])
    assert result.candidates[0].tax_evidence == "HALF_RATE"
    assert result.suspected_day_trade_qty == 1000
    assert result.candidates[0].tax_rule_version == TAX_RULES_VERSION
    assert result.rules_version == "tw_sec_tax_v3"
    assert result.candidates[0].instrument_class == "INFERRED_TW_COMMON_STOCK"
    assert result.candidates[0].classification_basis == "symbol_heuristic_4digit"
    # 啟發式不得自稱已確認普通股
    assert result.candidates[0].instrument_class != "TW_COMMON_STOCK"
    assert "verified" not in result.candidates[0].classification_basis.lower()


def test_cr02_etf_symbol_insufficient_evidence() -> None:
    """CR-02：ETF（00xx）不得套用股票減半稅 → INSUFFICIENT_EVIDENCE。"""
    buy = _trade("b1", "2025-04-11", "BUY", 1000, "100", tax="0", symbol="0050", name="合成ETF")
    # 數值若硬套股票減半會是 HALF_RATE
    sell = _trade(
        "s1", "2025-04-11", "SELL", 1000, "100", tax="150", symbol="0050", name="合成ETF"
    )
    result = annotate_day_trades([buy, sell], allocations=[])
    assert result.candidates[0].tax_evidence == "INSUFFICIENT_EVIDENCE"
    assert result.suspected_day_trade_qty == 0
    assert result.candidates[0].instrument_class == "TW_ETF"
    assert result.candidates[0].classification_basis in {
        "symbol_heuristic_4digit",
        "name_keyword",
    }


def test_cr02_etf_name_keyword_insufficient_evidence() -> None:
    """CR-02：名稱含 ETF 關鍵字 → INSUFFICIENT；basis=name_keyword。"""
    buy = _trade("b1", "2025-04-13", "BUY", 1000, "100", tax="0", symbol="1234", name="合成ETF基金")
    sell = _trade(
        "s1", "2025-04-13", "SELL", 1000, "100", tax="150", symbol="1234", name="合成ETF基金"
    )
    result = annotate_day_trades([buy, sell], allocations=[])
    assert result.candidates[0].tax_evidence == "INSUFFICIENT_EVIDENCE"
    assert result.candidates[0].instrument_class == "TW_ETF"
    assert result.candidates[0].classification_basis == "name_keyword"
    assert result.suspected_day_trade_qty == 0


def test_cr02_unknown_instrument_insufficient_evidence() -> None:
    """CR-02：未知商品型別 → INSUFFICIENT_EVIDENCE。"""
    buy = _trade("b1", "2025-04-12", "BUY", 1000, "100", tax="0", symbol="ABC")
    sell = _trade("s1", "2025-04-12", "SELL", 1000, "100", tax="150", symbol="ABC")
    result = annotate_day_trades([buy, sell], allocations=[])
    assert result.candidates[0].tax_evidence == "INSUFFICIENT_EVIDENCE"
    assert result.suspected_day_trade_qty == 0
    assert result.candidates[0].instrument_class == "UNKNOWN"
    assert result.candidates[0].classification_basis == "unknown"


def test_cr02_before_half_rate_effective_date_insufficient() -> None:
    """CR-02：減半稅生效日前不得判 HALF_RATE。"""
    # 生效日 2017-04-28；此前即使稅額像減半亦不足
    buy = _trade("b1", "2017-04-27", "BUY", 1000, "100", tax="0", symbol="2330")
    sell = _trade("s1", "2017-04-27", "SELL", 1000, "100", tax="150", symbol="2330")
    result = annotate_day_trades([buy, sell], allocations=[])
    assert result.candidates[0].tax_evidence == "INSUFFICIENT_EVIDENCE"
    assert result.suspected_day_trade_qty == 0


def test_cr02_on_half_rate_effective_date_allows_half() -> None:
    """CR-02：減半稅生效日當日可判 HALF_RATE。"""
    buy = _trade("b1", "2017-04-28", "BUY", 1000, "100", tax="0", symbol="2330")
    sell = _trade("s1", "2017-04-28", "SELL", 1000, "100", tax="150", symbol="2330")
    result = annotate_day_trades([buy, sell], allocations=[])
    assert result.candidates[0].tax_evidence == "HALF_RATE"
    assert result.suspected_day_trade_qty == 1000


def test_cr02_on_tax_rules_valid_through_allows_half() -> None:
    """CR-02：規則有效窗末日仍可 HALF_RATE。"""
    buy = _trade("b1", "2026-12-31", "BUY", 1000, "100", tax="0", symbol="2330")
    sell = _trade("s1", "2026-12-31", "SELL", 1000, "100", tax="150", symbol="2330")
    result = annotate_day_trades([buy, sell], allocations=[])
    assert result.candidates[0].tax_evidence == "HALF_RATE"
    assert result.suspected_day_trade_qty == 1000


def test_cr02_after_tax_rules_valid_through_insufficient() -> None:
    """CR-02：規則有效窗次日／未來未知規則 → INSUFFICIENT_EVIDENCE。"""
    buy = _trade("b1", "2027-01-01", "BUY", 1000, "100", tax="0", symbol="2330")
    sell = _trade("s1", "2027-01-01", "SELL", 1000, "100", tax="150", symbol="2330")
    result = annotate_day_trades([buy, sell], allocations=[])
    assert result.candidates[0].tax_evidence == "INSUFFICIENT_EVIDENCE"
    assert result.candidates[0].annotation_status == "INSUFFICIENT_EVIDENCE"
    assert result.suspected_day_trade_qty == 0


def test_cr02_audit_records_classification_and_rounding() -> None:
    """CR-02：audit 記錄 classification_basis／有效窗／取整與容差依據。"""
    buy = _trade("b1", "2025-04-14", "BUY", 1000, "100", tax="0", symbol="2330")
    sell = _trade("s1", "2025-04-14", "SELL", 1000, "100", tax="150", symbol="2330")
    result = annotate_day_trades([buy, sell], allocations=[])
    payload = annotation_to_audit_dict(result)["day_trade_annotation"]
    assert payload["rules_version"] == "tw_sec_tax_v3"
    assert payload["tax_rounding"] == "ROUND_HALF_UP"
    assert payload["tax_tolerance_twd"] == 1
    assert payload["tax_rules_valid_through"] == "2026-12-31"
    assert "INFERRED_TW_COMMON_STOCK" in payload["eligible_instrument_classes"]
    assert "TW_COMMON_STOCK" not in payload["eligible_instrument_classes"]
    cand = payload["candidates"][0]
    assert cand["instrument_class"] == "INFERRED_TW_COMMON_STOCK"
    assert cand["classification_basis"] == "symbol_heuristic_4digit"
    ev = cand["sell_tax_evidences"][0]
    assert ev["instrument_class"] == "INFERRED_TW_COMMON_STOCK"
    assert ev["classification_basis"] == "symbol_heuristic_4digit"


def test_cr03_ambiguous_when_both_rates_within_tolerance() -> None:
    """CR-03：|tax-half|≤tol 且 |tax-full|≤tol → AMBIGUOUS；優先於 HALF_RATE；不標 SUSPECTED。"""
    # gross=200 → half=0.3→0（ROUND_HALF_UP? 0.3→0）、full=0.6→1；選小額使兩者皆≤1
    # gross=333 → half=0.4995→0、full=0.999→1；tax=0 可同時近 half 與接近 full 邊緣
    # 更直接：gross=1 → half=0.0015→0、full=0.003→0；tax=0 兩者皆≤tol
    buy = _trade("b1", "2025-04-06", "BUY", 1, "1", tax="0")
    sell = _trade("s1", "2025-04-06", "SELL", 1, "1", tax="0")
    result = annotate_day_trades([buy, sell], allocations=[])

    assert len(result.candidates) == 1
    cand = result.candidates[0]
    assert cand.tax_evidence == "AMBIGUOUS_TAX_EVIDENCE"
    assert cand.annotation_status != "SUSPECTED_DAY_TRADE"
    assert cand.suspected_support_qty == 0
    assert result.suspected_day_trade_qty == 0


def test_cr03_group_with_ambiguous_not_suspected() -> None:
    """CR-03：組內含 AMBIGUOUS 則整組不標 SUSPECTED。"""
    buy = _trade("b1", "2025-04-07", "BUY", 200, "100", tax="0")
    sell_half = _trade("s_half", "2025-04-07", "SELL", 100, "100", tax="15")
    sell_amb = _trade("s_amb", "2025-04-07", "SELL", 1, "1", tax="0")
    result = annotate_day_trades([buy, sell_half, sell_amb], allocations=[])

    assert result.candidates[0].tax_evidence == "AMBIGUOUS_TAX_EVIDENCE"
    assert result.candidates[0].annotation_status != "SUSPECTED_DAY_TRADE"
    assert result.suspected_day_trade_qty == 0


def test_cr04_annotation_failure_wrapped_emits_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    """CR-04：內部邏輯拋錯 → ANNOTATION_FAILED warning；不拋出。"""
    from backend.services import day_trade_annotation as mod

    def _boom(*_a, **_k):
        raise RuntimeError("synthetic annotation fault")

    monkeypatch.setattr(mod, "_sell_tax_evidence", _boom)
    trades = [
        _trade("b1", "2025-04-08", "BUY", 100, "100", tax="0"),
        _trade("s1", "2025-04-08", "SELL", 100, "100", tax="15"),
    ]
    result = annotate_day_trades(trades, allocations=[])
    assert result.suspected_day_trade_qty == 0
    assert result.candidates == []
    assert any(w.startswith("ANNOTATION_FAILED:") for w in result.warnings)


def test_cr04_annotation_failure_on_iterable_materialization() -> None:
    """CR-04：trades 迭代失敗 → 可追溯警告；不得拋錯。"""

    class _BadIter:
        def __iter__(self):
            raise ValueError("boom")

    result = annotate_day_trades(_BadIter(), allocations=[])  # type: ignore[arg-type]
    assert result.suspected_day_trade_qty == 0
    assert result.same_day_reconciled_qty == 0
    assert any(w.startswith("ANNOTATION_FAILED:") for w in result.warnings)


def test_h01_annotation_on_off_financial_fields_equal() -> None:
    """H01／CR-09：財務鍵 snapshot 後跑 annotation；allocations／blocking／unsold 全等。"""
    trades_mit = [
        _mit(_trade("b1", "2025-03-20", "BUY", 1000, "72", tax="0"), 1),
        _mit(_trade("s1", "2025-03-20", "SELL", 1000, "70", tax="105"), 2),
    ]
    domain_trades = [
        _trade("b1", "2025-03-20", "BUY", 1000, "72", tax="0"),
        _trade("s1", "2025-03-20", "SELL", 1000, "70", tax="105"),
    ]

    match = run_fifo("h01", trades_mit)
    snapshot = {
        "allocs": [
            (a.buy_trade_id, a.sell_trade_id, a.quantity, a.match_type)
            for a in match.allocations
        ],
        "blocking": match.blocking,
        "unsold": [(u.buy_trade_id, u.available) for u in match.unsold],
        "buy_gross": [t.gross_amount for t in domain_trades if t.side == "BUY"],
        "sell_gross": [t.gross_amount for t in domain_trades if t.side == "SELL"],
        "commission": [t.commission for t in domain_trades],
        "tax": [t.tax for t in domain_trades],
    }

    ann = annotate_day_trades(domain_trades, match.allocations)

    assert [
        (a.buy_trade_id, a.sell_trade_id, a.quantity, a.match_type) for a in match.allocations
    ] == snapshot["allocs"]
    assert match.blocking == snapshot["blocking"]
    assert [(u.buy_trade_id, u.available) for u in match.unsold] == snapshot["unsold"]
    assert [t.gross_amount for t in domain_trades if t.side == "BUY"] == snapshot["buy_gross"]
    assert [t.gross_amount for t in domain_trades if t.side == "SELL"] == snapshot["sell_gross"]
    assert [t.commission for t in domain_trades] == snapshot["commission"]
    assert [t.tax for t in domain_trades] == snapshot["tax"]
    assert isinstance(ann.candidates, list)
    assert all(isinstance(a, Allocation) for a in match.allocations)


def test_cr12_audit_dict_includes_trace_fields() -> None:
    """CR-12：audit candidate 區分 same_day／half_rate ids 與逐筆稅證據。"""
    buy = _trade("b1", "2025-04-09", "BUY", 1000, "100", tax="0")
    sell_half = _trade("s1", "2025-04-09", "SELL", 400, "100", tax="60")
    sell_full = _trade("s2", "2025-04-09", "SELL", 600, "100", tax="180")
    allocs = [
        Allocation(
            run_id="r1",
            allocation_id="a1",
            buy_trade_id="b1",
            opening_lot_id=None,
            sell_trade_id="s1",
            quantity=400,
            sequence_no=1,
            match_type="SAME_DAY_RECONCILED",
        )
    ]
    result = annotate_day_trades([buy, sell_half, sell_full], allocs)
    payload = annotation_to_audit_dict(result)
    cand = payload["day_trade_annotation"]["candidates"][0]
    assert set(cand["same_day_sell_trade_ids"]) == {"s1", "s2"}
    assert set(cand["half_rate_sell_trade_ids"]) == {"s1"}
    assert set(cand["candidate_sell_trade_ids"]) == {"s1"}  # 僅 HALF_RATE 候選
    assert set(cand["source_buy_trade_ids"]) == {"b1"}
    assert set(cand["source_row_ids"]) == {"src-b1", "src-s1", "src-s2"}
    assert cand["half_rate_sell_qty"] == 400
    assert cand["suspected_support_qty"] == 400
    assert cand["reconciled_quantity"] == 400
    assert "uncertainty_reason" in cand
    assert cand["tax_rule_version"] == TAX_RULES_VERSION
    by_id = {e["trade_id"]: e for e in cand["sell_tax_evidences"]}
    assert by_id["s1"]["tax_evidence"] == "HALF_RATE"
    assert by_id["s2"]["tax_evidence"] == "STANDARD_RATE"
    assert by_id["s1"]["source_row_id"] == "src-s1"
