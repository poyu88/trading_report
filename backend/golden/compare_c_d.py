"""獨立 C 層與實際 D 層輸出比對（CR-10A）。

不得以 D 反推或覆寫 C；內部 trade_id 字串可不相同，改以來源指紋對應。
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from typing import Any

from backend.util.decimal_text import normalize_decimal_text


def _d(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal(0)
    text = normalize_decimal_text(str(value))
    return Decimal(text) if text not in ("",) else Decimal(0)


def trade_source_fingerprint(
    *,
    symbol: str,
    trade_date: str,
    side: str,
    quantity: int,
    unit_price: Any,
    gross_amount: Any,
    commission: Any,
    tax: Any,
    interest: Any = "0",
) -> str:
    """以來源可觀測欄位建立穩定指紋（正規化 Decimal 文字）。"""
    date_norm = str(trade_date).replace("/", "-")
    parts = [
        str(symbol).strip(),
        date_norm,
        str(side).strip().upper(),
        str(int(quantity)),
        normalize_decimal_text(str(unit_price)),
        normalize_decimal_text(str(gross_amount)),
        normalize_decimal_text(str(commission)),
        normalize_decimal_text(str(tax)),
        normalize_decimal_text(str(interest or "0")),
    ]
    return "|".join(parts)


def allocation_line_finance_rows(expected_c: dict[str, Any]) -> list[dict[str, Any]]:
    """由獨立 C ``allocation_lines``＋來源指紋組出逐筆 expected（禁從 Excel 反推）。"""
    id_to_fp = _c_trade_fp_map(expected_c)
    id_to_meta = {
        str(t["source_trade_id"]): t for t in (expected_c.get("trade_fingerprints") or [])
    }
    rows: list[dict[str, Any]] = []
    for line in expected_c.get("allocation_lines") or []:
        buy_id = str(line.get("buy_trade_id") or "")
        sell_id = str(line.get("sell_trade_id") or "")
        buy = id_to_meta.get(buy_id) or {}
        sell = id_to_meta.get(sell_id) or {}
        buy_fp = id_to_fp.get(buy_id, buy_id)
        sell_fp = id_to_fp.get(sell_id, sell_id)
        qty = int(line.get("quantity") or 0)
        match_type = str(line.get("match_type") or "")
        identity = f"{match_type}|{buy_fp}|{sell_fp}|{qty}"
        rows.append(
            {
                "identity_key": identity,
                "match_type": match_type,
                "quantity": qty,
                "buy_fp": buy_fp,
                "sell_fp": sell_fp,
                "symbol": str(line.get("symbol") or buy.get("symbol") or ""),
                "buy_date": str(buy.get("trade_date") or "").replace("/", "-"),
                "sell_date": str(sell.get("trade_date") or "").replace("/", "-"),
                "buy_unit_price": str(buy.get("unit_price") or ""),
                "sell_unit_price": str(sell.get("unit_price") or ""),
                "cost": _d(line.get("cost")),
                "income": _d(line.get("income")),
                "realized_pnl": _d(line.get("realized_pnl")),
                "buy_commission_applied": _d(line.get("buy_commission_applied")),
                "sell_commission_applied": _d(line.get("sell_commission_applied")),
                "sell_tax_applied": _d(line.get("sell_tax_applied")),
                "sell_interest_applied": _d(line.get("sell_interest_applied")),
            }
        )
    return sorted(rows, key=lambda r: r["identity_key"])


def golden_finance_from_expected_c(expected_c: dict[str, Any]) -> dict[str, Any]:
    """將 C 層 aggregates／allocation_lines 對映為財務 golden（含逐筆）。"""
    agg = expected_c.get("aggregates") or {}
    realized = expected_c.get("realized_and_open") or {}
    buy_gross = _d(agg.get("buy_gross_amount"))
    sell_gross = _d(agg.get("sell_gross_amount"))
    buy_commission = _d(agg.get("buy_commission"))
    sell_commission = _d(agg.get("sell_commission"))
    tax = _d(agg.get("tax"))
    interest = _d(agg.get("interest"))
    per_rows = allocation_line_finance_rows(expected_c)
    open_cost = (
        _d(realized.get("open_cost"))
        if realized.get("status") == "COMPUTED"
        else Decimal(0)
    )
    if per_rows:
        matched_cost = sum((r["cost"] for r in per_rows), Decimal(0))
        income = sum((r["income"] for r in per_rows), Decimal(0))
        # 明細 Excel 成本加總含未售列；與 C matched＋open_cost 對齊
        cost = matched_cost + open_cost
    else:
        matched_cost = buy_gross + buy_commission
        income = sell_gross - sell_commission - tax - interest
        cost = matched_cost + open_cost
    if realized.get("status") == "COMPUTED" and realized.get("realized_pnl") is not None:
        profit = _d(realized["realized_pnl"])
    else:
        profit = income - matched_cost
    sell_count = int(agg.get("sell_trade_count") or 0)
    return {
        "buy_qty": _d(agg.get("buy_quantity")),
        "sell_qty": _d(agg.get("sell_quantity")),
        "buy_gross": buy_gross,
        "sell_gross": sell_gross,
        "commission": buy_commission + sell_commission,
        "buy_commission": buy_commission,
        "sell_commission": sell_commission,
        "tax": tax,
        "interest": interest,
        "cost": cost,
        "income": income,
        "unsold_qty": _d((expected_c.get("fifo_expected") or {}).get("unsold_buy_qty")),
        "remaining_inventory_cost": open_cost,
        "min_detail_rows": Decimal(max(len(per_rows), sell_count, 1)),
        "expected_report_profit": profit,
        # 逐筆：直接來自 C allocation_lines（依 identity 排序，非 Excel 反推）
        "per_row_costs": [r["cost"] for r in per_rows],
        "per_row_incomes": [r["income"] for r in per_rows],
        "per_row_lines": per_rows,
    }


def compare_allocation_lines_to_trace_rows(
    expected_c: dict[str, Any],
    trace_rows: list[dict[str, Any]],
    *,
    trade_id_to_fp: dict[str, str],
) -> dict[str, Any]:
    """以來源指紋對應 Trace MATCHED 列與 C allocation_lines（逐筆財務）。

    使用多重集（非單值 dict）比對，避免重複配對鍵被覆蓋而遺失明細。
    """
    from collections import Counter, defaultdict

    expected = allocation_line_finance_rows(expected_c)
    actual_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in trace_rows:
        if str(row.get("row_kind") or "") != "MATCHED":
            continue
        buy_fp = trade_id_to_fp.get(str(row.get("buy_trade_id") or ""), "")
        sell_fp = trade_id_to_fp.get(str(row.get("sell_trade_id") or ""), "")
        qty = int(row.get("quantity") or 0)
        match_type = str(row.get("match_type") or "")
        key = f"{match_type}|{buy_fp}|{sell_fp}|{qty}"
        actual_by_key[key].append(row)

    diffs: dict[str, dict[str, str]] = {}
    errors: list[str] = []
    if not expected:
        errors.append("no_expected_allocation_lines")

    exp_counter = Counter(r["identity_key"] for r in expected)
    act_counter = Counter(
        {k: len(v) for k, v in actual_by_key.items()}
    )
    # Counter 對缺失鍵視為 0；改以完整多重集相等
    if exp_counter != act_counter:
        diffs["line_identity_multiset"] = {
            "expected_counts": str(dict(sorted(exp_counter.items()))),
            "actual_counts": str(dict(sorted(act_counter.items()))),
            "expected_only": str(
                sorted(k for k in exp_counter if exp_counter[k] > act_counter.get(k, 0))
            ),
            "actual_only": str(
                sorted(k for k in act_counter if act_counter[k] > exp_counter.get(k, 0))
            ),
        }

    field_pairs = (
        ("cost", "cost"),
        ("income", "income"),
        ("realized_pnl", "profit"),
        ("sell_commission_applied", "commission"),
        ("sell_tax_applied", "tax"),
        ("sell_interest_applied", "interest"),
    )
    # 依鍵分組 expected，與 actual 列表逐筆對位（同鍵內順序穩定）
    exp_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for exp in expected:
        exp_by_key[exp["identity_key"]].append(exp)
    for key, exp_list in exp_by_key.items():
        act_list = actual_by_key.get(key) or []
        for i, exp in enumerate(exp_list):
            if i >= len(act_list):
                break
            act = act_list[i]
            for exp_field, act_field in field_pairs:
                ev = _d(exp[exp_field])
                av = _d(act.get(act_field))
                if ev != av:
                    diffs[f"{key}#{i}:{exp_field}"] = {
                        "expected": str(ev),
                        "actual": str(av),
                    }

    actual_matched_count = sum(len(v) for v in actual_by_key.values())
    if len(expected) != actual_matched_count:
        diffs["line_count"] = {
            "expected": str(len(expected)),
            "actual": str(actual_matched_count),
        }
    return {
        "ok": not diffs and not errors,
        "diffs": diffs,
        "errors": errors,
        "expected_line_count": len(expected),
        "actual_matched_count": actual_matched_count,
    }


def build_actual_d_from_pipeline(
    *,
    trade_count: int,
    buy_qty: int,
    sell_qty: int,
    buy_gross: Decimal,
    sell_gross: Decimal,
    buy_commission: Decimal,
    sell_commission: Decimal,
    tax: Decimal,
    interest: Decimal,
    cost: Decimal,
    income: Decimal,
    realized_pnl: Decimal,
    open_quantity: int,
    open_cost: Decimal,
    standard_fifo_qty: int,
    same_day_qty: int,
    unmatched_sell_qty: int,
    unsold_buy_qty: int,
    allocation_fingerprints: list[dict[str, Any]],
    trade_fingerprints: list[str],
) -> dict[str, Any]:
    """組裝 D 層可比對摘要（由正式管線觀測值構成）。"""
    return {
        "trade_count": trade_count,
        "buy_qty": buy_qty,
        "sell_qty": sell_qty,
        "buy_gross": buy_gross,
        "sell_gross": sell_gross,
        "buy_commission": buy_commission,
        "sell_commission": sell_commission,
        "tax": tax,
        "interest": interest,
        "cost": cost,
        "income": income,
        "realized_pnl": realized_pnl,
        "open_quantity": open_quantity,
        "open_cost": open_cost,
        "standard_fifo_allocated_qty": standard_fifo_qty,
        "same_day_reconciled_qty": same_day_qty,
        "unmatched_sell_qty": unmatched_sell_qty,
        "unsold_buy_qty": unsold_buy_qty,
        "allocation_fingerprints": list(allocation_fingerprints),
        "trade_fingerprints": list(trade_fingerprints),
    }


def _c_trade_fp_map(expected_c: dict[str, Any]) -> dict[str, str]:
    """source_trade_id → fingerprint。"""
    out: dict[str, str] = {}
    for t in expected_c.get("trade_fingerprints") or []:
        fp = trade_source_fingerprint(
            symbol=str(t["symbol"]),
            trade_date=str(t["trade_date"]),
            side=str(t["side"]),
            quantity=int(t["quantity"]),
            unit_price=t["unit_price"],
            gross_amount=t["gross_amount"],
            commission=t["commission"],
            tax=t["tax"],
            interest=t.get("interest", "0"),
        )
        out[str(t["source_trade_id"])] = fp
    return out


def compare_expected_c_to_actual_d(
    expected_c: dict[str, Any],
    actual_d: dict[str, Any],
    *,
    require_allocation_match: bool = True,
) -> dict[str, Any]:
    """比對 C 與 D；不修改 ``expected_c``。

    Returns:
        ``{"ok": bool, "diffs": dict, "errors": list, "compared_fields": list}``
    """
    # 防禦：不得靜默覆寫 C
    _ = deepcopy(expected_c)
    diffs: dict[str, dict[str, str]] = {}
    errors: list[str] = []
    compared: list[str] = []

    integrity = (expected_c.get("source_integrity") or {}).get("status")
    if integrity == "FAIL" or expected_c.get("validation_status") == "BLOCKED_SOURCE_INTEGRITY":
        errors.append("expected_c_blocked_source_integrity")
        return {"ok": False, "diffs": diffs, "errors": errors, "compared_fields": compared}

    agg = expected_c.get("aggregates") or {}
    fifo = expected_c.get("fifo_expected") or {}
    realized = expected_c.get("realized_and_open") or {}

    def _check(name: str, exp: Any, act: Any) -> None:
        compared.append(name)
        ev = _d(exp) if not isinstance(exp, int) else Decimal(exp)
        av = _d(act) if not isinstance(act, int) else Decimal(act)
        if ev != av:
            diffs[name] = {"expected": str(ev), "actual": str(av)}

    _check("valid_trade_count", agg.get("valid_trade_count"), actual_d.get("trade_count"))
    _check("buy_quantity", agg.get("buy_quantity"), actual_d.get("buy_qty"))
    _check("sell_quantity", agg.get("sell_quantity"), actual_d.get("sell_qty"))
    _check("buy_gross_amount", agg.get("buy_gross_amount"), actual_d.get("buy_gross"))
    _check("sell_gross_amount", agg.get("sell_gross_amount"), actual_d.get("sell_gross"))
    _check("buy_commission", agg.get("buy_commission"), actual_d.get("buy_commission"))
    _check("sell_commission", agg.get("sell_commission"), actual_d.get("sell_commission"))
    _check("tax", agg.get("tax"), actual_d.get("tax"))
    if agg.get("interest_known", True):
        _check("interest", agg.get("interest"), actual_d.get("interest"))
    _check(
        "standard_fifo_allocated_qty",
        fifo.get("standard_fifo_allocated_qty"),
        actual_d.get("standard_fifo_allocated_qty"),
    )
    _check(
        "same_day_reconciled_qty",
        fifo.get("same_day_reconciled_qty"),
        actual_d.get("same_day_reconciled_qty"),
    )
    _check(
        "unmatched_sell_qty",
        fifo.get("unmatched_sell_qty"),
        actual_d.get("unmatched_sell_qty"),
    )
    _check("unsold_buy_qty", fifo.get("unsold_buy_qty"), actual_d.get("unsold_buy_qty"))
    if realized.get("status") == "COMPUTED":
        _check("realized_pnl", realized.get("realized_pnl"), actual_d.get("realized_pnl"))
        _check("open_quantity", realized.get("open_quantity"), actual_d.get("open_quantity"))
        open_status = str(actual_d.get("open_cost_status") or "VERIFIED")
        compared.append("open_cost")
        if open_status in {"NOT_VERIFIED", "PENDING_DATA"}:
            errors.append(f"open_cost_{open_status.lower()}")
        else:
            ev = _d(realized.get("open_cost"))
            av = _d(actual_d.get("open_cost"))
            if ev != av:
                diffs["open_cost"] = {"expected": str(ev), "actual": str(av)}
        gfin = golden_finance_from_expected_c(expected_c)
        _check("cost", gfin["cost"], actual_d.get("cost"))
        _check("income", gfin["income"], actual_d.get("income"))

    # 來源交易指紋集合（不要求內部 ID 字串相同）
    c_fps = set(_c_trade_fp_map(expected_c).values())
    if c_fps:
        compared.append("trade_fingerprints")
        d_fps = set(actual_d.get("trade_fingerprints") or [])
        if c_fps != d_fps:
            diffs["trade_fingerprints"] = {
                "expected_only": str(sorted(c_fps - d_fps)),
                "actual_only": str(sorted(d_fps - c_fps)),
            }

    if require_allocation_match:
        id_to_fp = _c_trade_fp_map(expected_c)
        expected_allocs: list[tuple[str, str, str, int]] = []
        for a in expected_c.get("allocations") or []:
            buy_id = a.get("buy_trade_id")
            sell_id = a.get("sell_trade_id")
            buy_fp = id_to_fp.get(str(buy_id), str(buy_id))
            sell_fp = id_to_fp.get(str(sell_id), str(sell_id))
            expected_allocs.append(
                (str(a.get("match_type")), buy_fp, sell_fp, int(a.get("quantity") or 0))
            )
        actual_allocs = [
            (
                str(a.get("match_type")),
                str(a.get("buy_fp")),
                str(a.get("sell_fp")),
                int(a.get("quantity") or 0),
            )
            for a in (actual_d.get("allocation_fingerprints") or [])
        ]
        compared.append("allocation_fingerprints")
        if sorted(expected_allocs) != sorted(actual_allocs):
            diffs["allocation_fingerprints"] = {
                "expected_count": str(len(expected_allocs)),
                "actual_count": str(len(actual_allocs)),
            }

    ok = not diffs and not errors
    return {"ok": ok, "diffs": diffs, "errors": errors, "compared_fields": compared}
