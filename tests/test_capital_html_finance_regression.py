"""群益 statement_html_v1 財務合成回歸（防 HIST-01）。

對照 docs/test/RCA_capital_fifo_finance.md：部分配對不得吃全額價金、
費用一次、W 註記、exceptions 守恆欄、早賣缺期初 DRAFT。

本檔為特徵化／回歸安全網（行為已於玉山財務修復後存在），非虛構 RED。
僅使用合成 HTML；禁止讀寫正式 DB／真實對帳單。
"""

from __future__ import annotations

import csv
import json
from decimal import Decimal
from html import escape
from pathlib import Path

from openpyxl import load_workbook

from backend.db.repositories import find_account_by_label
from backend.domain.exceptions import BlockingExceptionError
from backend.reports.field_schema import HEADERS
from backend.services.allocation_service import match_fifo_for_account
from backend.services.import_service import apply_import
from backend.services.report_finance import PARTIAL_MATCH_NOTE
from backend.services.report_service import generate_detail_report


def _write_html(
    path: Path,
    rows: list[dict[str, str | int]],
    *,
    with_totals: bool = False,
) -> Path:
    """合成群益 HTML 偽 XLS（.stockCode／.stockName）。"""
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
        side = str(r["side"])
        side_label = "現股買進" if side == "BUY" else "現股賣出"
        px = Decimal(str(r["price"]))
        qty = int(r["qty"])
        gross = Decimal(str(r.get("gross", px * qty)))
        fee = Decimal(str(r.get("commission", "0")))
        tax = Decimal(str(r.get("tax", "0")))
        interest = Decimal(str(r.get("interest", "0")))
        if "net" in r:
            net = Decimal(str(r["net"]))
        elif side == "BUY":
            net = -(gross + fee)
        else:
            net = gross - fee - tax - interest
        stock = (
            f'<td><span class="stockCode">{escape(str(r["symbol"]))}</span> '
            f'<span class="stockName">{escape(str(r.get("name", "合成")))}</span></td>'
        )
        rest = [
            str(r["date"]),
            side_label,
            "臺幣",
            str(r["price"]),
            str(qty),
            f"{gross}",
            f"{fee}",
            f"{tax}",
            f"{net}",
            "0",
            "0",
            f"{interest}",
            "0",
            "0",
            "0",
            "0",
            "TDD",
        ]
        chunks.append("<tr>" + stock + "".join(f"<td>{escape(x)}</td>" for x in rest) + "</tr>")
    if with_totals:
        chunks.append(
            "<tr>"
            + "<td>總合(臺幣)</td>"
            + "".join("<td></td>" for _ in range(17))
            + "</tr>"
        )
        chunks.append(
            "<tr>"
            + "<td>總合(人民幣)</td>"
            + "".join("<td></td>" for _ in range(17))
            + "</tr>"
        )
    chunks.append("</table></body></html>")
    path.write_text("".join(chunks), encoding="utf-8")
    return path


def _import_match_report(
    db_session,
    tmp_path: Path,
    rows: list[dict[str, str | int]],
    *,
    allow_partial: bool = True,
    with_totals: bool = True,
):
    path = _write_html(tmp_path / "capital_synth.xls", rows, with_totals=with_totals)
    result = apply_import(db_session, path, "群益", "main", "statement_html_v1")
    db_session.commit()
    account = find_account_by_label(db_session, "main")
    assert account is not None
    _run, match = match_fifo_for_account(db_session, account.id)
    db_session.commit()
    out = tmp_path / "out"
    xlsx, audit, exc = generate_detail_report(
        db_session, account.id, out, allow_partial=allow_partial
    )
    db_session.commit()
    return result, match, xlsx, audit, exc, out


def test_hist01_partial_sell_income_is_fragment_not_full_gross(
    db_session, tmp_path: Path
) -> None:
    """買 1000、賣 2000 → 已配收入＝半額價金−費稅，不得＝全額−費稅。"""
    rows = [
        {
            "symbol": "3260",
            "name": "合成威",
            "date": "2025/11/01",
            "side": "BUY",
            "price": "10",
            "qty": 1000,
            "commission": "20",
        },
        {
            "symbol": "3260",
            "name": "合成威",
            "date": "2025/12/01",
            "side": "SELL",
            "price": "15",
            "qty": 2000,
            "commission": "30",
            "tax": "90",
            "interest": "0",
        },
    ]
    result, match, xlsx, audit, exc, out = _import_match_report(
        db_session, tmp_path, rows, allow_partial=True
    )
    assert result.trade_count == 2
    assert result.excluded_count == 2
    assert match.blocking
    assert sum(a.quantity for a in match.allocations) == 1000

    wb = load_workbook(xlsx, data_only=True)
    ws = wb.active
    assert [c.value for c in ws[1]] == HEADERS
    assert ws.max_column == 23

    data = list(ws.iter_rows(min_row=2, values_only=True))
    sold = [r for r in data if r[9] is not None]  # 股數（賣）
    assert len(sold) == 1
    assert sold[0][9] == 1000
    # 片段價金 15000 − 30 − 90 − 0 = 14880；若 HIST-01 回歸會變成 29880
    assert Decimal(str(sold[0][16])) == Decimal(14880)
    assert sold[0][22] == PARTIAL_MATCH_NOTE
    # 絕不可接近全額收入
    assert Decimal(str(sold[0][16])) != Decimal(29880)

    audit_obj = json.loads(audit.read_text(encoding="utf-8"))
    assert audit_obj["draft"] is True
    assert audit_obj["conservation_ok"] is True

    exc_rows = list(csv.DictReader(exc.open(encoding="utf-8-sig")))
    assert len(exc_rows) == 1
    detail = json.loads(exc_rows[0]["detail_json"])
    assert detail["matched_quantity"] == 1000
    assert detail["unmatched_quantity"] == 1000
    assert Decimal(detail["matched_gross"]) == Decimal(15000)
    assert Decimal(detail["unmatched_gross"]) == Decimal(15000)
    assert Decimal(detail["source_gross"]) == Decimal(30000)
    assert detail["amount_conservation_ok"] is True

    cons = list(out.glob("價金費用守恆核對_*.csv"))
    assert cons
    cons_rows = list(csv.DictReader(cons[0].open(encoding="utf-8-sig")))
    assert cons_rows
    assert all(str(r.get("F_conservation_ok", "")).lower() == "true" for r in cons_rows)

    traces = list(out.glob("FIFO配對及未配對明細_*.xlsx"))
    assert traces
    tw = load_workbook(traces[0], data_only=True).active
    th = [c.value for c in tw[1]]
    kind_i = th.index("列語意")
    kinds = [r[kind_i] for r in tw.iter_rows(min_row=2, values_only=True)]
    assert "MATCHED" in kinds
    assert "UNMATCHED_SELL" in kinds


def test_html_multi_buy_fee_once_and_full_match(db_session, tmp_path: Path) -> None:
    """一賣配兩買：賣費／稅與各買費皆只出現一次；無 blocking。"""
    rows = [
        {
            "symbol": "1111",
            "name": "測一",
            "date": "2025/01/01",
            "side": "BUY",
            "price": "10",
            "qty": 1000,
            "commission": "20",
        },
        {
            "symbol": "1111",
            "name": "測一",
            "date": "2025/01/02",
            "side": "BUY",
            "price": "12",
            "qty": 500,
            "commission": "10",
        },
        {
            "symbol": "1111",
            "name": "測一",
            "date": "2025/01/03",
            "side": "SELL",
            "price": "15",
            "qty": 1200,
            "commission": "18",
            "tax": "36",
        },
    ]
    result, match, xlsx, _audit, _exc, _out = _import_match_report(
        db_session, tmp_path, rows, allow_partial=False, with_totals=False
    )
    assert result.trade_count == 3
    assert not match.blocking
    assert sum(a.quantity for a in match.allocations) == 1200

    wb = load_workbook(xlsx, data_only=True)
    ws = wb.active
    data = list(ws.iter_rows(min_row=2, values_only=True))
    assert "DRAFT" not in xlsx.name

    buy_fees = [Decimal(str(r[7] or 0)) for r in data]
    sell_fees = [Decimal(str(r[10] or 0)) for r in data if r[10] is not None]
    sell_taxes = [Decimal(str(r[11] or 0)) for r in data if r[11] is not None]
    assert sum(buy_fees) == Decimal(30)  # 20+10，各一次
    assert sum(1 for f in buy_fees if f != 0) == 2
    assert sum(sell_fees) == Decimal(18)
    assert sum(sell_taxes) == Decimal(36)
    assert sum(1 for f in sell_fees if f != 0) == 1


def test_html_income_deducts_nonzero_interest_on_first_fragment(
    db_session, tmp_path: Path
) -> None:
    """全額配對：收入扣手續費＋稅＋非零利息（HTML 路徑）。"""
    rows = [
        {
            "symbol": "3596",
            "name": "合成智",
            "date": "2025/02/01",
            "side": "BUY",
            "price": "100",
            "qty": 100,
            "commission": "10",
        },
        {
            "symbol": "3596",
            "name": "合成智",
            "date": "2025/02/10",
            "side": "SELL",
            "price": "110",
            "qty": 100,
            "commission": "12",
            "tax": "33",
            "interest": "5",
        },
    ]
    _result, match, xlsx, _audit, _exc, _out = _import_match_report(
        db_session, tmp_path, rows, allow_partial=False, with_totals=False
    )
    assert not match.blocking
    wb = load_workbook(xlsx, data_only=True)
    ws = wb.active
    sold = [r for r in ws.iter_rows(min_row=2, values_only=True) if r[9] is not None]
    assert len(sold) == 1
    # 11000 − 12 − 33 − 5 = 10950
    assert Decimal(str(sold[0][16])) == Decimal(10950)
    assert Decimal(str(sold[0][12])) == Decimal(5)  # 利息欄


def test_early_sell_blocks_formal_and_draft_lists_insufficient(
    db_session, tmp_path: Path
) -> None:
    """早於買進的賣出：正式擋、DRAFT 例外；主明細不造假已售列。"""
    rows = [
        {
            "symbol": "9991",
            "name": "合成甲",
            "date": "2025/10/03",
            "side": "SELL",
            "price": "100",
            "qty": 250,
            "commission": "40",
            "tax": "75",
        },
        {
            "symbol": "0050",
            "name": "合成乙",
            "date": "2025/10/20",
            "side": "BUY",
            "price": "50",
            "qty": 200,
            "commission": "20",
        },
    ]
    path = _write_html(tmp_path / "early.xls", rows, with_totals=True)
    apply_import(db_session, path, "群益", "main", "statement_html_v1")
    db_session.commit()
    account = find_account_by_label(db_session, "main")
    assert account is not None
    _run, match = match_fifo_for_account(db_session, account.id)
    db_session.commit()
    assert match.blocking
    assert any(i.issue_code == "INSUFFICIENT_PRIOR_BUYS" for i in match.issues)
    # 不得把 9991 賣出配到較晚的 0050 買進
    assert match.allocations == []

    out = tmp_path / "out"
    try:
        generate_detail_report(db_session, account.id, out, allow_partial=False)
        raised = False
    except BlockingExceptionError:
        raised = True
    assert raised

    xlsx, _audit, exc = generate_detail_report(
        db_session, account.id, out, allow_partial=True
    )
    db_session.commit()
    assert "DRAFT" in xlsx.name
    wb = load_workbook(xlsx, data_only=True)
    ws = wb.active
    # 主明細不應出現 9991 的已售配對列（無虛構買進）
    symbols = [r[2] for r in ws.iter_rows(min_row=2, values_only=True)]
    assert "9991" not in symbols
    assert "0050" in symbols

    exc_rows = list(csv.DictReader(exc.open(encoding="utf-8-sig")))
    assert any(r["code"] == "INSUFFICIENT_PRIOR_BUYS" for r in exc_rows)
    detail = json.loads(next(r for r in exc_rows if r["code"] == "INSUFFICIENT_PRIOR_BUYS")["detail_json"])
    assert detail["unmatched_quantity"] == 250
    assert Decimal(detail["unmatched_gross"]) == Decimal(25000)
    assert detail["matched_quantity"] == 0
