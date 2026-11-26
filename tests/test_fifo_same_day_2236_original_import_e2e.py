"""CR-06：原始九筆 2236 欄位 → Parser／Import → FIFO → Report → Audit。

匿名群益 HTML fixture；保留原始日期／價／量／價金／費／稅／淨收付。
不得以價×量覆蓋券商原始成交金額。正式 DB 不讀寫。

Canonical 列序來源：Owner 提供之原始檔陳述序（非 RCA／合成軌跡）。
- ``2024-08-28``：SELL(tax=145 半稅) → SELL(tax=290 全稅) → BUY
- ``2024-09-02``：SELL(579@111.5, gross=64558≠111.5×579) → SELL(21@112)
其他同日排列僅作 permutation；不得將非原始序宣稱為 Owner 原始序。
"""

from __future__ import annotations

import json
from copy import deepcopy
from decimal import Decimal
from html import escape
from pathlib import Path

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from backend.db.models import FifoAllocation, RawRow, TradeRow
from backend.db.repositories import find_account_by_label
from backend.domain.models import txt_to_decimal
from backend.reports.field_schema import HEADERS
from backend.services.allocation_service import match_fifo_for_account, quantity_conservation
from backend.services.import_service import apply_import
from backend.services.report_service import generate_detail_report

# Owner 提供之原始九筆欄位（匿名名稱；非真實帳戶識別）
# 兩筆 2024-08-28 同價同量但交易稅不同（145 vs 290）→ 不得錯誤去重
ORIGINAL_ROWS: list[dict[str, str | int]] = [
    {
        "symbol": "2236",
        "name": "合成2236",
        "date": "2024/08/05",
        "side": "BUY",
        "price": "105.5",
        "qty": 2000,
        "gross": "211000",
        "commission": "195",
        "tax": "0",
        "net": "-211195",
    },
    {
        "symbol": "2236",
        "name": "合成2236",
        "date": "2024/08/08",
        "side": "SELL",
        "price": "108",
        "qty": 400,
        "gross": "43200",
        "commission": "40",
        "tax": "129",
        "net": "43031",
    },
    {
        "symbol": "2236",
        "name": "合成2236",
        "date": "2024/08/12",
        "side": "BUY",
        "price": "106.5",
        "qty": 1000,
        "gross": "106500",
        "commission": "99",
        "tax": "0",
        "net": "-106599",
    },
    {
        "symbol": "2236",
        "name": "合成2236",
        "date": "2024/08/21",
        "side": "SELL",
        "price": "108",
        "qty": 1000,
        "gross": "108000",
        "commission": "100",
        "tax": "324",
        "net": "107576",
    },
    # Owner canonical 2024-08-28：半稅 SELL → 全稅 SELL → BUY
    {
        "symbol": "2236",
        "name": "合成2236",
        "date": "2024/08/28",
        "side": "SELL",
        "price": "96.8",
        "qty": 1000,
        "gross": "96800",
        "commission": "90",
        "tax": "145",
        "net": "96565",
    },
    {
        "symbol": "2236",
        "name": "合成2236",
        "date": "2024/08/28",
        "side": "SELL",
        "price": "96.8",
        "qty": 1000,
        "gross": "96800",
        "commission": "90",
        "tax": "290",
        "net": "96420",
    },
    {
        "symbol": "2236",
        "name": "合成2236",
        "date": "2024/08/28",
        "side": "BUY",
        "price": "98",
        "qty": 1000,
        "gross": "98000",
        "commission": "91",
        "tax": "0",
        "net": "-98091",
    },
    # Owner canonical 2024-09-02：579@111.5 → 21@112
    {
        "symbol": "2236",
        "name": "合成2236",
        "date": "2024/09/02",
        "side": "SELL",
        "price": "111.5",
        "qty": 579,
        "gross": "64558",
        "commission": "60",
        "tax": "193",
        "net": "64305",
    },
    {
        "symbol": "2236",
        "name": "合成2236",
        "date": "2024/09/02",
        "side": "SELL",
        "price": "112",
        "qty": 21,
        "gross": "2352",
        "commission": "2",
        "tax": "7",
        "net": "2343",
    },
]


def _golden_from_rows(rows: list[dict[str, str | int]]) -> dict[str, Decimal | int]:
    buy_qty = sell_qty = 0
    buy_gross = sell_gross = commission = tax = net = Decimal(0)
    buy_commission = sell_commission = Decimal(0)
    for r in rows:
        qty = int(r["qty"])
        g = Decimal(str(r["gross"]))
        c = Decimal(str(r["commission"]))
        tx = Decimal(str(r["tax"]))
        commission += c
        tax += tx
        net += Decimal(str(r["net"]))
        if r["side"] == "BUY":
            buy_qty += qty
            buy_gross += g
            buy_commission += c
        else:
            sell_qty += qty
            sell_gross += g
            sell_commission += c
    return {
        "raw_count": len(rows),
        "buy_qty": buy_qty,
        "sell_qty": sell_qty,
        "buy_gross": buy_gross,
        "sell_gross": sell_gross,
        "commission": commission,
        "buy_commission": buy_commission,
        "sell_commission": sell_commission,
        "tax": tax,
        "net_settlement_sum": net,
        # SPEC §7：全配平且費用一次落點時，報表損益加總 = 原始淨收付合計
        "expected_report_profit": sell_gross - buy_gross - commission - tax,
    }


def _golden_from_original() -> dict[str, Decimal | int]:
    return _golden_from_rows(ORIGINAL_ROWS)


def _permute_same_day(
    rows: list[dict[str, str | int]],
    day_slash: str,
    order_indices_within_day: list[int],
) -> list[dict[str, str | int]]:
    """依同日列相對序重排；其他日期列維持原相對位置。"""
    out = deepcopy(rows)
    day_positions = [i for i, r in enumerate(out) if r["date"] == day_slash]
    assert len(day_positions) == len(order_indices_within_day)
    day_rows = [out[i] for i in day_positions]
    reordered = [day_rows[j] for j in order_indices_within_day]
    for pos, row in zip(day_positions, reordered, strict=True):
        out[pos] = row
    return out


def _write_capital_html(path: Path, rows: list[dict[str, str | int]]) -> Path:
    headers = [
        "商品",
        "成交日",
        "買賣別",
        "幣別",
        "成交價",
        "成交股數",
        "成交金額",
        "手續費",
        "交易稅",
        "淨收付",
        "融資金額/擔保價款",
        "自備款/保證金",
        "利息",
        "融券手續費",
        "標借費",
        "證所稅",
        "健保費",
        "下單來源別",
    ]
    chunks = ["<html><meta charset='UTF-8'><body><table>"]
    chunks.append("<tr>" + "".join(f"<td>{escape(h)}</td>" for h in headers) + "</tr>")
    for r in rows:
        side_label = "現股買進" if r["side"] == "BUY" else "現股賣出"
        stock = (
            f'<td><span class="stockCode">{escape(str(r["symbol"]))}</span> '
            f'<span class="stockName">{escape(str(r["name"]))}</span></td>'
        )
        rest = [
            str(r["date"]),
            side_label,
            "臺幣",
            str(r["price"]),
            str(r["qty"]),
            str(r["gross"]),
            str(r["commission"]),
            str(r["tax"]),
            str(r["net"]),
            "0",
            "0",
            "0",
            "0",
            "0",
            "0",
            "0",
            "TDD",
        ]
        chunks.append("<tr>" + stock + "".join(f"<td>{escape(x)}</td>" for x in rest) + "</tr>")
    chunks.append("</table></body></html>")
    path.write_text("".join(chunks), encoding="utf-8")
    return path


def _run_pipeline(
    db_session,
    tmp_path: Path,
    rows: list[dict[str, str | int]],
    *,
    label: str,
):
    golden = _golden_from_rows(rows)
    path = _write_capital_html(tmp_path / f"{label}.xls", rows)
    result = apply_import(db_session, path, "群益", label, "statement_html_v1")
    db_session.commit()
    account = find_account_by_label(db_session, label)
    assert account is not None
    trades = list(db_session.scalars(select(TradeRow).where(TradeRow.account_id == account.id)))
    run, match = match_fifo_for_account(db_session, account.id)
    db_session.commit()
    alloc_rows = list(
        db_session.scalars(select(FifoAllocation).where(FifoAllocation.run_id == run.id))
    )
    out = tmp_path / f"out_{label}"
    xlsx, audit_path, exc_path = generate_detail_report(
        db_session, account.id, out, run_id=run.id, allow_partial=False
    )
    db_session.commit()
    return {
        "golden": golden,
        "import_result": result,
        "account": account,
        "trades": trades,
        "run": run,
        "match": match,
        "alloc_rows": alloc_rows,
        "xlsx": xlsx,
        "audit_path": audit_path,
        "exc_path": exc_path,
        "out": out,
    }


def _assert_core_invariants(ctx: dict, *, expect_suspected: bool = True) -> None:
    golden = ctx["golden"]
    trades = ctx["trades"]
    match = ctx["match"]
    assert ctx["import_result"].trade_count == 9
    assert len(trades) == 9
    assert golden["buy_qty"] == 4000
    assert golden["sell_qty"] == 4000

    buy_qty = sum(t.quantity for t in trades if t.side == "BUY")
    sell_qty = sum(t.quantity for t in trades if t.side == "SELL")
    assert buy_qty == 4000
    assert sell_qty == 4000

    by_type: dict[str, int] = {}
    for a in match.allocations:
        by_type[a.match_type] = by_type.get(a.match_type, 0) + a.quantity
    assert by_type.get("STANDARD_FIFO", 0) == 3600
    assert by_type.get("SAME_DAY_RECONCILED", 0) == 400
    assert sum(u.available for u in match.unsold) == 0
    assert not match.blocking
    assert not any(i.issue_code == "INSUFFICIENT_PRIOR_BUYS" for i in match.issues)
    assert quantity_conservation(trades, ctx["alloc_rows"])["ok"]

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

    audit = json.loads(ctx["audit_path"].read_text(encoding="utf-8"))
    ann = audit["day_trade_annotation"]
    if expect_suspected:
        assert ann["suspected_day_trade_qty"] == 1000
        assert ann["same_day_reconciled_qty"] == 400
        cand = next(c for c in ann["candidates"] if c["trade_date"] == "2024-08-28")
        assert cand["suspected_support_qty"] == 1000
        assert cand["half_rate_sell_qty"] == 1000
        assert cand["instrument_class"] == "INFERRED_TW_COMMON_STOCK"
        assert cand["classification_basis"] == "symbol_heuristic_4digit"


def _assert_excel_finance(ctx: dict) -> None:
    """CR-06B：實際 Excel A–W 財務加總 vs Decimal golden（canonical／permutation 共用）。"""
    golden = ctx["golden"]
    assert ctx["xlsx"].exists() and "DRAFT" not in ctx["xlsx"].name
    wb = load_workbook(ctx["xlsx"], data_only=True)
    ws = wb.active
    assert [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))] == HEADERS
    idx = {h: i for i, h in enumerate(HEADERS)}
    buy_comm_xlsx = sell_comm_xlsx = tax_xlsx = cost_xlsx = income_xlsx = profit_xlsx = Decimal(0)
    for row in ws.iter_rows(min_row=2, max_col=len(HEADERS), values_only=True):
        if row[idx["手續費（買）"]] is not None:
            buy_comm_xlsx += Decimal(str(row[idx["手續費（買）"]]))
        if row[idx["手續費（賣）"]] is not None:
            sell_comm_xlsx += Decimal(str(row[idx["手續費（賣）"]]))
        if row[idx["交易稅"]] is not None:
            tax_xlsx += Decimal(str(row[idx["交易稅"]]))
        if row[idx["成本"]] is not None:
            cost_xlsx += Decimal(str(row[idx["成本"]]))
        if row[idx["收入"]] is not None:
            income_xlsx += Decimal(str(row[idx["收入"]]))
        if row[idx["損益"]] is not None:
            profit_xlsx += Decimal(str(row[idx["損益"]]))

    assert buy_comm_xlsx == golden["buy_commission"]
    assert sell_comm_xlsx == golden["sell_commission"]
    assert tax_xlsx == golden["tax"]
    assert profit_xlsx == golden["expected_report_profit"]
    assert profit_xlsx == golden["net_settlement_sum"]
    assert income_xlsx - cost_xlsx == profit_xlsx


def _assert_per_trade_fees_from_trace(ctx: dict) -> None:
    """CR-06C：以實際 FIFO Trace（含 trade_id）核對逐筆費用落點。

    第一片段才認列手續費／稅；後續片段不得重複；跨 Pass1／Pass2 加總＝交易合計。
    """
    trades = ctx["trades"]
    golden = ctx["golden"]
    trade_by_id = {t.id: t for t in trades}
    allocs = sorted(ctx["alloc_rows"], key=lambda a: a.sequence_no)

    # 各來源交易已配對／未配對股數
    matched_sell: dict[str, int] = {}
    matched_buy: dict[str, int] = {}
    for a in allocs:
        if a.sell_trade_id:
            matched_sell[a.sell_trade_id] = matched_sell.get(a.sell_trade_id, 0) + a.allocated_quantity
        if a.buy_trade_id:
            matched_buy[a.buy_trade_id] = matched_buy.get(a.buy_trade_id, 0) + a.allocated_quantity
    for t in trades:
        if t.side == "SELL":
            assert matched_sell.get(t.id, 0) == t.quantity
        else:
            assert matched_buy.get(t.id, 0) == t.quantity

    trace = Path(json.loads(ctx["audit_path"].read_text(encoding="utf-8"))["fifo_trace_file"])
    assert trace.is_file()
    twb = load_workbook(trace, data_only=True)
    tws = twb.active
    theaders = [c.value for c in next(tws.iter_rows(min_row=1, max_row=1))]
    tidx = {h: i for i, h in enumerate(theaders)}
    assert "buy_trade_id" in tidx and "sell_trade_id" in tidx

    # 逐筆 SELL：Trace 上該 sell_trade_id 的手續費／稅加總＝原始交易（僅第一片段有值）
    sell_fee_from_trace: dict[str, Decimal] = {}
    sell_tax_from_trace: dict[str, Decimal] = {}
    buy_fee_from_trace: dict[str, Decimal] = {}
    fee_rows_by_sell: dict[str, int] = {}
    for row in tws.iter_rows(min_row=2, max_col=len(theaders), values_only=True):
        sid = row[tidx["sell_trade_id"]]
        bid = row[tidx["buy_trade_id"]]
        if sid:
            if row[tidx["手續費"]] is not None:
                fee = Decimal(str(row[tidx["手續費"]]))
                sell_fee_from_trace[sid] = sell_fee_from_trace.get(sid, Decimal(0)) + fee
                # 後續片段可能寫入 0（非 None）；僅非零列計為費用落點
                if fee != 0:
                    fee_rows_by_sell[sid] = fee_rows_by_sell.get(sid, 0) + 1
            if row[tidx["交易稅"]] is not None:
                sell_tax_from_trace[sid] = sell_tax_from_trace.get(sid, Decimal(0)) + Decimal(
                    str(row[tidx["交易稅"]])
                )
        if bid and row[tidx["手續費"]] is not None and not sid:
            # UNSOLD／BUY-only 列；本案例全配平，通常不走此路徑
            buy_fee_from_trace[bid] = buy_fee_from_trace.get(bid, Decimal(0)) + Decimal(
                str(row[tidx["手續費"]])
            )

    for t in trades:
        if t.side != "SELL":
            continue
        assert sell_fee_from_trace.get(t.id, Decimal(0)) == txt_to_decimal(t.commission_txt)
        assert sell_tax_from_trace.get(t.id, Decimal(0)) == txt_to_decimal(t.tax_txt)
        # 第一片段才有費用：該 sell 有費用的列恰為 1（若佣金>0）
        if txt_to_decimal(t.commission_txt) != 0:
            assert fee_rows_by_sell.get(t.id, 0) == 1

    assert sum(sell_fee_from_trace.values(), Decimal(0)) == golden["sell_commission"]
    assert sum(sell_tax_from_trace.values(), Decimal(0)) == golden["tax"]

    # BUY 手續費：由 detail Excel 第一買片段加總（Trace 賣列不帶買方手續費）
    wb = load_workbook(ctx["xlsx"], data_only=True)
    ws = wb.active
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    idx = {h: i for i, h in enumerate(headers)}
    buy_comm_xlsx = Decimal(0)
    for row in ws.iter_rows(min_row=2, max_col=len(headers), values_only=True):
        if row[idx["手續費（買）"]] is not None:
            buy_comm_xlsx += Decimal(str(row[idx["手續費（買）"]]))
    assert buy_comm_xlsx == golden["buy_commission"]

    # Pass1／Pass2：依 first allocation match_type 歸屬後加總＝交易合計
    first_sell_alloc: dict[str, FifoAllocation] = {}
    first_buy_alloc: dict[str, FifoAllocation] = {}
    for a in allocs:
        if a.sell_trade_id and a.sell_trade_id not in first_sell_alloc:
            first_sell_alloc[a.sell_trade_id] = a
        if a.buy_trade_id and a.buy_trade_id not in first_buy_alloc:
            first_buy_alloc[a.buy_trade_id] = a
    fee_comm_by_type: dict[str, Decimal] = {}
    fee_tax_by_type: dict[str, Decimal] = {}
    for sid, a in first_sell_alloc.items():
        t = trade_by_id[sid]
        mt = a.match_type
        fee_comm_by_type[mt] = fee_comm_by_type.get(mt, Decimal(0)) + txt_to_decimal(
            t.commission_txt
        )
        fee_tax_by_type[mt] = fee_tax_by_type.get(mt, Decimal(0)) + txt_to_decimal(t.tax_txt)
    for bid, a in first_buy_alloc.items():
        t = trade_by_id[bid]
        mt = a.match_type
        fee_comm_by_type[mt] = fee_comm_by_type.get(mt, Decimal(0)) + txt_to_decimal(
            t.commission_txt
        )
    assert sum(fee_comm_by_type.values(), Decimal(0)) == golden["commission"]
    assert sum(fee_tax_by_type.values(), Decimal(0)) == golden["tax"]
    assert set(fee_comm_by_type) <= {"STANDARD_FIFO", "SAME_DAY_RECONCILED"}


def test_cr06_canonical_owner_row_order() -> None:
    """CR-06A：ORIGINAL_ROWS 必須為 Owner 原始列序（非合成軌跡）。"""
    d0828 = [r for r in ORIGINAL_ROWS if r["date"] == "2024/08/28"]
    assert [r["side"] for r in d0828] == ["SELL", "SELL", "BUY"]
    assert [str(r["tax"]) for r in d0828] == ["145", "290", "0"]
    d0902 = [r for r in ORIGINAL_ROWS if r["date"] == "2024/09/02"]
    assert [int(r["qty"]) for r in d0902] == [579, 21]


def test_cr06_original_nine_row_parser_import_fifo_report(db_session, tmp_path: Path) -> None:
    """Parser→Import→FIFO→Report；Pass1=3600／Pass2=400／suspected=1000。"""
    ctx = _run_pipeline(db_session, tmp_path, ORIGINAL_ROWS, label="orig2236")
    trades = ctx["trades"]

    raw_ids = {t.raw_row_id for t in trades}
    assert len(raw_ids) == 9
    raw_ok = list(db_session.scalars(select(RawRow).where(RawRow.id.in_(raw_ids))))
    assert len(raw_ok) == 9

    by_key = {
        (t.trade_date, t.side, t.quantity, t.unit_price_txt, t.tax_txt): t for t in trades
    }
    for r in ORIGINAL_ROWS:
        day = str(r["date"]).replace("/", "-")
        key = (day, str(r["side"]), int(r["qty"]), str(r["price"]), str(r["tax"]))
        t = by_key[key]
        assert t.gross_amount_txt == str(r["gross"])
        assert t.commission_txt == str(r["commission"])
        assert t.tax_txt == str(r["tax"])
        assert t.net_settlement_txt == str(r["net"])

    same_day_sells = [
        t
        for t in trades
        if t.side == "SELL" and t.trade_date == "2024-08-28" and t.quantity == 1000
    ]
    assert len(same_day_sells) == 2
    assert {t.tax_txt for t in same_day_sells} == {"145", "290"}

    odd = next(t for t in trades if t.quantity == 579)
    assert odd.gross_amount_txt == "64558"
    assert Decimal(odd.unit_price_txt) * odd.quantity != Decimal(64558)

    _assert_core_invariants(ctx)
    assert ctx["xlsx"].exists() and ctx["audit_path"].exists() and ctx["exc_path"].exists()
    _assert_excel_finance(ctx)
    _assert_per_trade_fees_from_trace(ctx)

    audit = json.loads(ctx["audit_path"].read_text(encoding="utf-8"))
    cand = next(
        c for c in audit["day_trade_annotation"]["candidates"] if c["trade_date"] == "2024-08-28"
    )
    half_ids = set(cand["half_rate_sell_trade_ids"])
    assert len(half_ids) == 1
    assert next(t.tax_txt for t in trades if t.id in half_ids) == "145"
    assert len(cand["same_day_sell_trade_ids"]) == 2

    ctx2 = _run_pipeline(db_session, tmp_path, ORIGINAL_ROWS, label="orig2236b")
    _assert_core_invariants(ctx2)
    _assert_excel_finance(ctx2)
    by_type2: dict[str, int] = {}
    for a in ctx2["match"].allocations:
        by_type2[a.match_type] = by_type2.get(a.match_type, 0) + a.quantity
    assert by_type2.get("STANDARD_FIFO", 0) == 3600
    assert by_type2.get("SAME_DAY_RECONCILED", 0) == 400


@pytest.mark.parametrize(
    "label,rows",
    [
        (
            "perm0828_buy_first",
            _permute_same_day(ORIGINAL_ROWS, "2024/08/28", [2, 0, 1]),
        ),
        (
            "perm0828_full_then_half_then_buy",
            _permute_same_day(ORIGINAL_ROWS, "2024/08/28", [1, 0, 2]),
        ),
        (
            "perm0902_swap",
            _permute_same_day(ORIGINAL_ROWS, "2024/09/02", [1, 0]),
        ),
        (
            "perm_both_days_owner_inverse",
            _permute_same_day(
                _permute_same_day(ORIGINAL_ROWS, "2024/08/28", [2, 0, 1]),
                "2024/09/02",
                [1, 0],
            ),
        ),
    ],
)
def test_cr06_same_day_row_order_permutations(
    db_session, tmp_path: Path, label: str, rows: list[dict[str, str | int]]
) -> None:
    """同日列交換仍須核心不變量＋Excel 財務＋逐筆費用（CR-06B／C）。"""
    ctx = _run_pipeline(db_session, tmp_path, rows, label=label)
    _assert_core_invariants(ctx)
    _assert_excel_finance(ctx)
    _assert_per_trade_fees_from_trace(ctx)

    odd = next(t for t in ctx["trades"] if t.quantity == 579)
    assert odd.gross_amount_txt == "64558"
    assert Decimal(odd.unit_price_txt) * odd.quantity != Decimal(64558)

    taxes = {
        t.tax_txt
        for t in ctx["trades"]
        if t.side == "SELL" and t.trade_date == "2024-08-28" and t.quantity == 1000
    }
    assert taxes == {"145", "290"}
