"""CR-06：原始九筆 2236 欄位 → Parser／Import → FIFO → Report → Audit。

匿名群益 HTML fixture；保留原始日期／價／量／價金／費／稅／淨收付。
不得以價×量覆蓋券商原始成交金額。正式 DB 不讀寫。
"""

from __future__ import annotations

import json
from decimal import Decimal
from html import escape
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import select

from backend.db.models import FifoAllocation, RawRow, TradeRow
from backend.db.repositories import find_account_by_label
from backend.domain.models import txt_to_decimal
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
        "date": "2024/09/02",
        "side": "SELL",
        "price": "112",
        "qty": 21,
        "gross": "2352",
        "commission": "2",
        "tax": "7",
        "net": "2343",
    },
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
]


def _golden_from_original() -> dict[str, Decimal | int]:
    buy_qty = sell_qty = 0
    buy_gross = sell_gross = commission = tax = Decimal(0)
    for r in ORIGINAL_ROWS:
        qty = int(r["qty"])
        g = Decimal(str(r["gross"]))
        commission += Decimal(str(r["commission"]))
        tax += Decimal(str(r["tax"]))
        if r["side"] == "BUY":
            buy_qty += qty
            buy_gross += g
        else:
            sell_qty += qty
            sell_gross += g
    return {
        "raw_count": len(ORIGINAL_ROWS),
        "buy_qty": buy_qty,
        "sell_qty": sell_qty,
        "buy_gross": buy_gross,
        "sell_gross": sell_gross,
        "commission": commission,
        "tax": tax,
    }


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


def test_cr06_original_nine_row_parser_import_fifo_report(db_session, tmp_path: Path) -> None:
    """Parser→Import→FIFO→Report；Pass1=3600／Pass2=400／suspected=1000。"""
    golden = _golden_from_original()
    assert golden["buy_qty"] == 4000
    assert golden["sell_qty"] == 4000
    assert golden["raw_count"] == 9

    path = _write_capital_html(tmp_path / "capital_2236_original.xls", ORIGINAL_ROWS)
    result = apply_import(db_session, path, "群益", "orig2236", "statement_html_v1")
    db_session.commit()
    assert result.trade_count == 9

    account = find_account_by_label(db_session, "orig2236")
    assert account is not None
    trades = list(db_session.scalars(select(TradeRow).where(TradeRow.account_id == account.id)))
    assert len(trades) == 9
    raw_ids = {t.raw_row_id for t in trades}
    assert len(raw_ids) == 9
    raw_ok = list(db_session.scalars(select(RawRow).where(RawRow.id.in_(raw_ids))))
    assert len(raw_ok) == 9
    # 同價同量不同稅兩筆皆在庫
    same_day_sells = [
        t
        for t in trades
        if t.side == "SELL" and t.trade_date == "2024-08-28" and t.quantity == 1000
    ]
    assert len(same_day_sells) == 2
    taxes = {t.tax_txt for t in same_day_sells}
    assert taxes == {"145", "290"}

    # 不得以價×量覆寫原始成交金額（96.8*1000=96800 剛好相等，另驗 111.5*579）
    odd = next(t for t in trades if t.quantity == 579)
    assert odd.gross_amount_txt == "64558"
    assert Decimal(odd.unit_price_txt) * odd.quantity != Decimal(64558)  # 111.5*579=64558.5

    buy_qty = sum(t.quantity for t in trades if t.side == "BUY")
    sell_qty = sum(t.quantity for t in trades if t.side == "SELL")
    assert buy_qty == 4000
    assert sell_qty == 4000

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

    run, match = match_fifo_for_account(db_session, account.id)
    db_session.commit()
    by_type: dict[str, int] = {}
    for a in match.allocations:
        by_type[a.match_type] = by_type.get(a.match_type, 0) + a.quantity
    assert by_type.get("STANDARD_FIFO", 0) == 3600
    assert by_type.get("SAME_DAY_RECONCILED", 0) == 400
    assert sum(u.available for u in match.unsold) == 0
    assert not match.blocking
    assert not any(i.issue_code == "INSUFFICIENT_PRIOR_BUYS" for i in match.issues)

    alloc_rows = list(
        db_session.scalars(select(FifoAllocation).where(FifoAllocation.run_id == run.id))
    )
    assert quantity_conservation(trades, alloc_rows)["ok"]

    out = tmp_path / "out"
    xlsx, audit_path, exc_path = generate_detail_report(
        db_session, account.id, out, run_id=run.id, allow_partial=False
    )
    db_session.commit()
    assert xlsx.exists() and audit_path.exists() and exc_path.exists()
    assert "DRAFT" not in xlsx.name
    # 報表可開啟
    wb = load_workbook(xlsx, data_only=True)
    assert wb.active.max_row >= 2

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    ann = audit["day_trade_annotation"]
    assert ann["suspected_day_trade_qty"] == 1000
    assert ann["same_day_reconciled_qty"] == 400
    cand = next(c for c in ann["candidates"] if c["trade_date"] == "2024-08-28")
    assert cand["suspected_support_qty"] == 1000
    assert cand["half_rate_sell_qty"] == 1000
    half_ids = set(cand["half_rate_sell_trade_ids"])
    assert len(half_ids) == 1
    half_tax = next(t.tax_txt for t in trades if t.id in half_ids)
    assert half_tax == "145"
    assert len(cand["same_day_sell_trade_ids"]) == 2
