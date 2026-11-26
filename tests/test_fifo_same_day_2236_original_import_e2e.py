"""CR-06：原始九筆 REAL_DERIVED → Parser／Import → FIFO → Report → Audit。

SOURCE: REAL_DERIVED（私有 fixture；禁止嵌入公開 Git）
- 列資料與私人財務答案位於 ``data/golden/private_fixtures/original_rows_2236.json``（gitignore）。
- 公開 CI 缺檔 → ``PRIVATE_FIXTURE_UNAVAILABLE`` skip；不得宣告 PASS。
- 本機有檔 → 必須完整執行；保留 FIFO／費用第一片段／Excel 財務邏輯。
- 名稱「合成2236」僅匿名標籤；非 price×qty 合成軌跡。
- 非零利息真實樣本：PENDING_DATA。
- 正式 DB 不讀寫；失敗訊息不輸出私人財務數值。
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
from backend.golden.expected_c import build_expected_c_document
from backend.reports.field_schema import HEADERS
from backend.services.allocation_service import match_fifo_for_account, quantity_conservation
from backend.services.import_service import apply_import
from backend.services.report_finance import allocate_trade_fragment_amounts
from backend.services.report_service import generate_detail_report
from tests.private_fixtures import (
    ORIGINAL_ROWS_2236_PATH,
    assert_priv_equal,
    assert_priv_true,
    load_original_rows_2236,
    private_fixture_unavailable_reason,
)

pytestmark = pytest.mark.skipif(
    not ORIGINAL_ROWS_2236_PATH.is_file(),
    reason=private_fixture_unavailable_reason(ORIGINAL_ROWS_2236_PATH),
)

ORIGINAL_ROWS, EXPECTED = (
    load_original_rows_2236()
    if ORIGINAL_ROWS_2236_PATH.is_file()
    else ([], {})
)


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


def _permute_same_day(
    rows: list[dict[str, str | int]],
    day_slash: str,
    order_indices_within_day: list[int],
) -> list[dict[str, str | int]]:
    """依同日列相對序重排；其他日期列維持原相對位置。"""
    out = deepcopy(rows)
    day_positions = [i for i, r in enumerate(out) if r["date"] == day_slash]
    assert_priv_equal(len(day_positions), len(order_indices_within_day), "permute_day_len")
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
        "rows": rows,
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
    assert_priv_equal(ctx["import_result"].trade_count, EXPECTED["raw_count"], "import_trade_count")
    assert_priv_equal(len(trades), EXPECTED["raw_count"], "trade_len")
    assert_priv_equal(golden["buy_qty"], EXPECTED["buy_qty"], "golden_buy_qty")
    assert_priv_equal(golden["sell_qty"], EXPECTED["sell_qty"], "golden_sell_qty")

    buy_qty = sum(t.quantity for t in trades if t.side == "BUY")
    sell_qty = sum(t.quantity for t in trades if t.side == "SELL")
    assert_priv_equal(buy_qty, EXPECTED["buy_qty"], "sum_buy_qty")
    assert_priv_equal(sell_qty, EXPECTED["sell_qty"], "sum_sell_qty")

    by_type: dict[str, int] = {}
    for a in match.allocations:
        by_type[a.match_type] = by_type.get(a.match_type, 0) + a.quantity
    assert_priv_equal(
        by_type.get("STANDARD_FIFO", 0), EXPECTED["standard_fifo_qty"], "pass1_qty"
    )
    assert_priv_equal(
        by_type.get("SAME_DAY_RECONCILED", 0),
        EXPECTED["same_day_reconciled_qty"],
        "pass2_qty",
    )
    assert_priv_equal(sum(u.available for u in match.unsold), 0, "unsold")
    assert_priv_true(not match.blocking, "not_blocking")
    assert_priv_true(
        not any(i.issue_code == "INSUFFICIENT_PRIOR_BUYS" for i in match.issues),
        "no_insufficient",
    )
    assert_priv_true(quantity_conservation(trades, ctx["alloc_rows"])["ok"], "qty_conservation")

    buy_gross = sum(
        (txt_to_decimal(t.gross_amount_txt) for t in trades if t.side == "BUY"), Decimal(0)
    )
    sell_gross = sum(
        (txt_to_decimal(t.gross_amount_txt) for t in trades if t.side == "SELL"), Decimal(0)
    )
    commission = sum((txt_to_decimal(t.commission_txt) for t in trades), Decimal(0))
    tax = sum((txt_to_decimal(t.tax_txt) for t in trades), Decimal(0))
    assert_priv_equal(buy_gross, golden["buy_gross"], "buy_gross")
    assert_priv_equal(sell_gross, golden["sell_gross"], "sell_gross")
    assert_priv_equal(commission, golden["commission"], "commission")
    assert_priv_equal(tax, golden["tax"], "tax")

    audit = json.loads(ctx["audit_path"].read_text(encoding="utf-8"))
    ann = audit["day_trade_annotation"]
    if expect_suspected:
        assert_priv_equal(
            ann["suspected_day_trade_qty"],
            EXPECTED["suspected_day_trade_qty"],
            "suspected_qty",
        )
        assert_priv_equal(
            ann["same_day_reconciled_qty"],
            EXPECTED["same_day_reconciled_qty"],
            "ann_pass2_qty",
        )
        cand = next(
            c for c in ann["candidates"] if c["trade_date"] == EXPECTED["triple_day_iso"]
        )
        assert_priv_equal(
            cand["suspected_support_qty"],
            EXPECTED["suspected_day_trade_qty"],
            "suspected_support",
        )
        assert_priv_equal(
            cand["half_rate_sell_qty"],
            EXPECTED["triple_sell_qty"],
            "half_rate_sell_qty",
        )
        assert_priv_equal(cand["instrument_class"], "INFERRED_TW_COMMON_STOCK", "instrument")
        assert_priv_equal(
            cand["classification_basis"], "symbol_heuristic_4digit", "class_basis"
        )


def _assert_excel_finance(ctx: dict) -> None:
    """CR-06B：實際 Excel A–W 財務加總 vs Decimal golden（canonical／permutation 共用）。"""
    golden = ctx["golden"]
    assert_priv_true(ctx["xlsx"].exists() and "DRAFT" not in ctx["xlsx"].name, "xlsx_final")
    wb = load_workbook(ctx["xlsx"], data_only=True)
    ws = wb.active
    assert_priv_equal(
        [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))], HEADERS, "headers"
    )
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

    assert_priv_equal(buy_comm_xlsx, golden["buy_commission"], "xlsx_buy_comm")
    assert_priv_equal(sell_comm_xlsx, golden["sell_commission"], "xlsx_sell_comm")
    assert_priv_equal(tax_xlsx, golden["tax"], "xlsx_tax")
    assert_priv_equal(profit_xlsx, golden["expected_report_profit"], "xlsx_profit")
    assert_priv_equal(profit_xlsx, golden["net_settlement_sum"], "xlsx_profit_vs_net")
    assert_priv_equal(income_xlsx - cost_xlsx, profit_xlsx, "xlsx_income_cost")


def _fixture_rows_to_expected_c_input(
    rows: list[dict[str, str | int]],
) -> list[dict[str, object]]:
    """將既有 canonical／permutation fixture 轉為獨立 C 列（不新增虛假交易）。"""
    out: list[dict[str, object]] = []
    for i, r in enumerate(rows):
        out.append(
            {
                "source_id": "cr06c_fixture",
                "symbol": str(r["symbol"]),
                "trade_date": str(r["date"]),
                "side": str(r["side"]),
                "side_raw": "現股買進" if r["side"] == "BUY" else "現股賣出",
                "quantity": str(r["qty"]),
                "unit_price": str(r["price"]),
                "gross_amount": str(r["gross"]),
                "commission": str(r["commission"]),
                "tax": str(r["tax"]),
                "interest": "0",
                "net_settlement": str(r["net"]),
                "physical_line": i + 2,
                "trade_type": "CASH",
                "currency": "TWD",
                "account_id": "cr06c",
            }
        )
    return out


def _assert_independent_c_fee_on_first_fragment(ctx: dict) -> None:
    """以獨立 C allocation_lines 驗證買賣手續費／稅／已知利息只落在第一片段。"""
    golden = ctx["golden"]
    c_rows = _fixture_rows_to_expected_c_input(ctx["rows"])
    doc = build_expected_c_document(
        case_id="CR-06C-fixture",
        source_sha256="not_locked",
        source_path="data/golden/private_fixtures/original_rows_2236.json",
        source_format="private_real_derived_fixture",
        applicable_spec=["SPEC§6", "SPEC§7"],
        rows=c_rows,
        known_limitations=["interest_all_zero_in_fixture; nonzero_interest_PENDING_DATA"],
    )
    lines = sorted(doc["allocation_lines"], key=lambda x: int(x["sequence_no"]))
    assert_priv_true(bool(lines), "c_lines_nonempty")

    seen_sell: set[str] = set()
    seen_buy: set[str] = set()
    buy_fee_c = sell_fee_c = tax_c = interest_c = Decimal(0)
    for line in lines:
        sid = str(line["sell_trade_id"])
        bid = str(line["buy_trade_id"])
        sell_fee = Decimal(str(line["sell_commission_applied"]))
        buy_fee = Decimal(str(line["buy_commission_applied"]))
        tax = Decimal(str(line["sell_tax_applied"]))
        interest_raw = line["sell_interest_applied"]
        interest = Decimal(0) if interest_raw == "UNKNOWN" else Decimal(str(interest_raw))

        if sid not in seen_sell:
            seen_sell.add(sid)
            assert_priv_true(sell_fee >= 0 and tax >= 0, "first_sell_fee_nonneg")
            sell_fee_c += sell_fee
            tax_c += tax
            interest_c += interest
        else:
            assert_priv_equal(sell_fee, 0, "later_sell_fee")
            assert_priv_equal(tax, 0, "later_sell_tax")
            assert_priv_equal(interest, 0, "later_sell_interest")

        if bid not in seen_buy:
            seen_buy.add(bid)
            buy_fee_c += buy_fee
        else:
            assert_priv_equal(buy_fee, 0, "later_buy_fee")

        assert_priv_true(line["gross_conservation_ok"] is True, "c_gross_ok")

    assert_priv_equal(buy_fee_c, golden["buy_commission"], "c_buy_fee")
    assert_priv_equal(sell_fee_c, golden["sell_commission"], "c_sell_fee")
    assert_priv_equal(tax_c, golden["tax"], "c_tax")
    assert_priv_equal(interest_c, Decimal(0), "c_interest_zero")
    assert_priv_equal(
        Decimal(str(doc["aggregates"]["buy_commission"])),
        golden["buy_commission"],
        "c_agg_buy",
    )
    assert_priv_equal(
        Decimal(str(doc["aggregates"]["sell_commission"])),
        golden["sell_commission"],
        "c_agg_sell",
    )
    assert_priv_equal(Decimal(str(doc["aggregates"]["tax"])), golden["tax"], "c_agg_tax")


def _assert_per_trade_fees_from_trace(ctx: dict) -> None:
    """CR-06C：Trace／Excel／獨立 C 證明費用落在第一配對片段。"""
    trades = ctx["trades"]
    golden = ctx["golden"]
    trade_by_id = {t.id: t for t in trades}
    allocs = sorted(ctx["alloc_rows"], key=lambda a: a.sequence_no)
    alloc_by_id = {a.id: a for a in allocs}

    matched_sell: dict[str, int] = {}
    matched_buy: dict[str, int] = {}
    sell_allocs: dict[str, list[FifoAllocation]] = {}
    buy_allocs: dict[str, list[FifoAllocation]] = {}
    for a in allocs:
        if a.sell_trade_id:
            matched_sell[a.sell_trade_id] = matched_sell.get(a.sell_trade_id, 0) + a.allocated_quantity
            sell_allocs.setdefault(a.sell_trade_id, []).append(a)
        if a.buy_trade_id:
            matched_buy[a.buy_trade_id] = matched_buy.get(a.buy_trade_id, 0) + a.allocated_quantity
            buy_allocs.setdefault(a.buy_trade_id, []).append(a)
    for t in trades:
        if t.side == "SELL":
            assert_priv_equal(matched_sell.get(t.id, 0), t.quantity, "sell_matched_qty")
        else:
            assert_priv_equal(matched_buy.get(t.id, 0), t.quantity, "buy_matched_qty")

    for sid, alist in sell_allocs.items():
        t = trade_by_id[sid]
        frag = allocate_trade_fragment_amounts(
            txt_to_decimal(t.unit_price_txt),
            txt_to_decimal(t.gross_amount_txt),
            [a.allocated_quantity for a in alist],
            trade_id=t.id,
        )
        assert_priv_true(
            frag.conservation_ok or abs(frag.difference) <= Decimal(1),
            "frag_conservation",
        )

    first_sell_alloc: dict[str, FifoAllocation] = {
        sid: alist[0] for sid, alist in sell_allocs.items()
    }
    first_buy_alloc: dict[str, FifoAllocation] = {
        bid: alist[0] for bid, alist in buy_allocs.items()
    }

    trace = Path(json.loads(ctx["audit_path"].read_text(encoding="utf-8"))["fifo_trace_file"])
    assert_priv_true(trace.is_file(), "trace_exists")
    twb = load_workbook(trace, data_only=True)
    tws = twb.active
    theaders = [c.value for c in next(tws.iter_rows(min_row=1, max_row=1))]
    tidx = {h: i for i, h in enumerate(theaders)}
    assert_priv_true(
        "buy_trade_id" in tidx and "sell_trade_id" in tidx and "allocation_id" in tidx,
        "trace_headers",
    )

    matched_by_sell: dict[str, list[tuple[int, object]]] = {}
    sell_fee_from_trace: dict[str, Decimal] = {}
    sell_tax_from_trace: dict[str, Decimal] = {}
    sell_interest_from_trace: dict[str, Decimal] = {}
    for row in tws.iter_rows(min_row=2, max_col=len(theaders), values_only=True):
        if str(row[tidx["列語意"]] or "") != "MATCHED":
            continue
        sid = row[tidx["sell_trade_id"]]
        aid = row[tidx["allocation_id"]]
        assert_priv_true(bool(sid) and bool(aid) and aid in alloc_by_id, "trace_ids")
        seq = int(alloc_by_id[aid].sequence_no)
        matched_by_sell.setdefault(str(sid), []).append((seq, row))

        fee = Decimal(str(row[tidx["手續費"]] or 0))
        tax = Decimal(str(row[tidx["交易稅"]] or 0))
        interest = (
            Decimal(str(row[tidx["利息"]]))
            if row[tidx["利息"]] is not None
            else Decimal(0)
        )
        sell_fee_from_trace[str(sid)] = sell_fee_from_trace.get(str(sid), Decimal(0)) + fee
        sell_tax_from_trace[str(sid)] = sell_tax_from_trace.get(str(sid), Decimal(0)) + tax
        sell_interest_from_trace[str(sid)] = (
            sell_interest_from_trace.get(str(sid), Decimal(0)) + interest
        )

    for t in trades:
        if t.side != "SELL":
            continue
        sid = t.id
        rows_for_sell = sorted(matched_by_sell.get(sid, []), key=lambda x: x[0])
        assert_priv_true(bool(rows_for_sell), "matched_trace_sell")
        first_aid = first_sell_alloc[sid].id
        exp_fee = txt_to_decimal(t.commission_txt)
        exp_tax = txt_to_decimal(t.tax_txt)
        exp_interest = txt_to_decimal(t.interest_txt)

        for _seq, row in rows_for_sell:
            aid = row[tidx["allocation_id"]]
            fee = Decimal(str(row[tidx["手續費"]] or 0))
            tax = Decimal(str(row[tidx["交易稅"]] or 0))
            interest_cell = row[tidx["利息"]]
            interest = Decimal(str(interest_cell)) if interest_cell is not None else Decimal(0)
            if aid == first_aid:
                assert_priv_equal(fee, exp_fee, "first_frag_fee")
                assert_priv_equal(tax, exp_tax, "first_frag_tax")
                assert_priv_equal(interest, exp_interest, "first_frag_interest")
                assert_priv_true(interest_cell is not None, "interest_cell_present")
            else:
                assert_priv_equal(fee, 0, "later_frag_fee")
                assert_priv_equal(tax, 0, "later_frag_tax")
                assert_priv_equal(interest, 0, "later_frag_interest")

        assert_priv_equal(sell_fee_from_trace.get(sid, Decimal(0)), exp_fee, "trace_fee_sum")
        assert_priv_equal(sell_tax_from_trace.get(sid, Decimal(0)), exp_tax, "trace_tax_sum")
        assert_priv_equal(
            sell_interest_from_trace.get(sid, Decimal(0)),
            exp_interest,
            "trace_interest_sum",
        )

    assert_priv_equal(
        sum(sell_fee_from_trace.values(), Decimal(0)),
        golden["sell_commission"],
        "trace_sell_comm_total",
    )
    assert_priv_equal(
        sum(sell_tax_from_trace.values(), Decimal(0)), golden["tax"], "trace_tax_total"
    )
    assert_priv_equal(
        sum(sell_interest_from_trace.values(), Decimal(0)),
        sum((txt_to_decimal(t.interest_txt) for t in trades if t.side == "SELL"), Decimal(0)),
        "trace_interest_total",
    )

    wb = load_workbook(ctx["xlsx"], data_only=True)
    ws = wb.active
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    idx = {h: i for i, h in enumerate(headers)}
    buy_comm_xlsx = sell_comm_xlsx = tax_xlsx = Decimal(0)
    buy_nonzero_rows = 0
    sell_nonzero_fee_rows = 0
    for row in ws.iter_rows(min_row=2, max_col=len(headers), values_only=True):
        if row[idx["手續費（買）"]] is not None:
            bfee = Decimal(str(row[idx["手續費（買）"]]))
            buy_comm_xlsx += bfee
            if bfee != 0:
                buy_nonzero_rows += 1
        if row[idx["手續費（賣）"]] is not None:
            sfee = Decimal(str(row[idx["手續費（賣）"]]))
            sell_comm_xlsx += sfee
            if sfee != 0:
                sell_nonzero_fee_rows += 1
        if row[idx["交易稅"]] is not None:
            tax_xlsx += Decimal(str(row[idx["交易稅"]]))
    assert_priv_equal(buy_comm_xlsx, golden["buy_commission"], "xlsx2_buy_comm")
    assert_priv_equal(sell_comm_xlsx, golden["sell_commission"], "xlsx2_sell_comm")
    assert_priv_equal(tax_xlsx, golden["tax"], "xlsx2_tax")
    buy_count = sum(1 for t in trades if t.side == "BUY")
    sell_with_fee = sum(
        1 for t in trades if t.side == "SELL" and txt_to_decimal(t.commission_txt) != 0
    )
    assert_priv_equal(buy_nonzero_rows, buy_count, "buy_nonzero_rows")
    assert_priv_equal(sell_nonzero_fee_rows, sell_with_fee, "sell_nonzero_fee_rows")

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
    assert_priv_equal(
        sum(fee_comm_by_type.values(), Decimal(0)),
        golden["commission"],
        "fee_by_type_comm",
    )
    assert_priv_equal(
        sum(fee_tax_by_type.values(), Decimal(0)), golden["tax"], "fee_by_type_tax"
    )
    assert_priv_true(
        set(fee_comm_by_type) <= {"STANDARD_FIFO", "SAME_DAY_RECONCILED"},
        "fee_types_allowed",
    )

    _assert_independent_c_fee_on_first_fragment(ctx)
    assert_priv_true(quantity_conservation(trades, ctx["alloc_rows"])["ok"], "qty_cons_final")


def test_cr06_canonical_owner_row_order() -> None:
    """CR-06A：私有 ORIGINAL_ROWS 必須符合 Owner 原始列序元資料。"""
    d_triple = [r for r in ORIGINAL_ROWS if r["date"] == EXPECTED["triple_day_slash"]]
    assert_priv_equal([r["side"] for r in d_triple], EXPECTED["triple_sides"], "triple_sides")
    assert_priv_equal([str(r["tax"]) for r in d_triple], EXPECTED["triple_taxes"], "triple_taxes")
    d_odd = [r for r in ORIGINAL_ROWS if r["date"] == EXPECTED["odd_day_slash"]]
    assert_priv_equal([int(r["qty"]) for r in d_odd], EXPECTED["odd_qtys"], "odd_qtys")


@pytest.mark.skip(
    reason=(
        "PENDING_DATA: CR-06C 缺少非零利息真實樣本；"
        "本 REAL_DERIVED fixture 利息皆 0。資料齊全後：以真實非零利息列"
        "重跑 Trace／Excel／獨立 C 第一片段落點驗收並移除此 skip。"
    )
)
def test_cr06c_nonzero_interest_first_fragment_pending_data() -> None:
    """占位：非零利息第一片段落點（目前無可靠資料，不得填 0 冒充 PASS）。"""
    raise AssertionError("unreachable: should remain skipped until PENDING_DATA resolved")


def test_cr06_original_nine_row_parser_import_fifo_report(db_session, tmp_path: Path) -> None:
    """Parser→Import→FIFO→Report；Pass1／Pass2／suspected 對齊私有 expected。"""
    ctx = _run_pipeline(db_session, tmp_path, ORIGINAL_ROWS, label="orig2236")
    trades = ctx["trades"]

    raw_ids = {t.raw_row_id for t in trades}
    assert_priv_equal(len(raw_ids), EXPECTED["raw_count"], "raw_ids")
    raw_ok = list(db_session.scalars(select(RawRow).where(RawRow.id.in_(raw_ids))))
    assert_priv_equal(len(raw_ok), EXPECTED["raw_count"], "raw_ok")

    by_key = {
        (t.trade_date, t.side, t.quantity, t.unit_price_txt, t.tax_txt): t for t in trades
    }
    for r in ORIGINAL_ROWS:
        day = str(r["date"]).replace("/", "-")
        key = (day, str(r["side"]), int(r["qty"]), str(r["price"]), str(r["tax"]))
        t = by_key[key]
        assert_priv_equal(t.gross_amount_txt, str(r["gross"]), "row_gross")
        assert_priv_equal(t.commission_txt, str(r["commission"]), "row_commission")
        assert_priv_equal(t.tax_txt, str(r["tax"]), "row_tax")
        assert_priv_equal(t.net_settlement_txt, str(r["net"]), "row_net")

    same_day_sells = [
        t
        for t in trades
        if t.side == "SELL"
        and t.trade_date == EXPECTED["triple_day_iso"]
        and t.quantity == EXPECTED["triple_sell_qty"]
    ]
    assert_priv_equal(len(same_day_sells), 2, "same_day_sell_count")
    assert_priv_equal(
        {t.tax_txt for t in same_day_sells},
        {EXPECTED["half_tax"], EXPECTED["full_tax"]},
        "same_day_taxes",
    )

    odd = next(t for t in trades if t.quantity == EXPECTED["odd_primary_qty"])
    assert_priv_equal(odd.gross_amount_txt, EXPECTED["odd_primary_gross"], "odd_gross")
    assert_priv_true(
        Decimal(odd.unit_price_txt) * odd.quantity != Decimal(EXPECTED["odd_primary_gross"]),
        "odd_gross_ne_price_qty",
    )

    _assert_core_invariants(ctx)
    assert_priv_true(
        ctx["xlsx"].exists() and ctx["audit_path"].exists() and ctx["exc_path"].exists(),
        "artifacts",
    )
    _assert_excel_finance(ctx)
    _assert_per_trade_fees_from_trace(ctx)

    audit = json.loads(ctx["audit_path"].read_text(encoding="utf-8"))
    cand = next(
        c
        for c in audit["day_trade_annotation"]["candidates"]
        if c["trade_date"] == EXPECTED["triple_day_iso"]
    )
    half_ids = set(cand["half_rate_sell_trade_ids"])
    assert_priv_equal(len(half_ids), 1, "half_ids_len")
    assert_priv_equal(
        next(t.tax_txt for t in trades if t.id in half_ids),
        EXPECTED["half_tax"],
        "half_tax_match",
    )
    assert_priv_equal(len(cand["same_day_sell_trade_ids"]), 2, "same_day_sell_ids")

    ctx2 = _run_pipeline(db_session, tmp_path, ORIGINAL_ROWS, label="orig2236b")
    _assert_core_invariants(ctx2)
    _assert_excel_finance(ctx2)
    by_type2: dict[str, int] = {}
    for a in ctx2["match"].allocations:
        by_type2[a.match_type] = by_type2.get(a.match_type, 0) + a.quantity
    assert_priv_equal(
        by_type2.get("STANDARD_FIFO", 0), EXPECTED["standard_fifo_qty"], "pass1_rerun"
    )
    assert_priv_equal(
        by_type2.get("SAME_DAY_RECONCILED", 0),
        EXPECTED["same_day_reconciled_qty"],
        "pass2_rerun",
    )


def _perm_cases() -> list[tuple[str, list[dict[str, str | int]]]]:
    if not ORIGINAL_ROWS:
        return [("unavailable", [])]
    day_t = EXPECTED["triple_day_slash"]
    day_o = EXPECTED["odd_day_slash"]
    return [
        ("perm_triple_buy_first", _permute_same_day(ORIGINAL_ROWS, day_t, [2, 0, 1])),
        (
            "perm_triple_full_then_half_then_buy",
            _permute_same_day(ORIGINAL_ROWS, day_t, [1, 0, 2]),
        ),
        ("perm_odd_swap", _permute_same_day(ORIGINAL_ROWS, day_o, [1, 0])),
        (
            "perm_both_days_owner_inverse",
            _permute_same_day(
                _permute_same_day(ORIGINAL_ROWS, day_t, [2, 0, 1]),
                day_o,
                [1, 0],
            ),
        ),
    ]


@pytest.mark.parametrize("label,rows", _perm_cases())
def test_cr06_same_day_row_order_permutations(
    db_session, tmp_path: Path, label: str, rows: list[dict[str, str | int]]
) -> None:
    """同日列交換仍須核心不變量＋Excel 財務＋逐筆費用（CR-06B／C）。"""
    ctx = _run_pipeline(db_session, tmp_path, rows, label=label)
    _assert_core_invariants(ctx)
    _assert_excel_finance(ctx)
    _assert_per_trade_fees_from_trace(ctx)

    odd = next(t for t in ctx["trades"] if t.quantity == EXPECTED["odd_primary_qty"])
    assert_priv_equal(odd.gross_amount_txt, EXPECTED["odd_primary_gross"], "perm_odd_gross")
    assert_priv_true(
        Decimal(odd.unit_price_txt) * odd.quantity != Decimal(EXPECTED["odd_primary_gross"]),
        "perm_odd_ne_pxq",
    )

    taxes = {
        t.tax_txt
        for t in ctx["trades"]
        if t.side == "SELL"
        and t.trade_date == EXPECTED["triple_day_iso"]
        and t.quantity == EXPECTED["triple_sell_qty"]
    }
    assert_priv_equal(taxes, {EXPECTED["half_tax"], EXPECTED["full_tax"]}, "perm_taxes")
