"""Phase 3／CR-10A：合成路徑 C↔D（正式 Import／FIFO／Report；禁改 C）。"""

from __future__ import annotations

from decimal import Decimal
from html import escape
from pathlib import Path

from backend.db.session import init_db, make_session_factory
from backend.golden.compare_c_d import compare_expected_c_to_actual_d
from backend.golden.expected_c import build_expected_c_document
from backend.golden.phase3_pipeline import run_import_match_report


def _write_html(path: Path, rows: list[dict[str, str | int]]) -> Path:
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


def _rows_for_c(rows: list[dict[str, str | int]]) -> list[dict]:
    out = []
    for i, r in enumerate(rows, start=2):
        out.append(
            {
                "source_id": "syn_phase3",
                "account_id": "syn_acct",
                "physical_line": i,
                "symbol": str(r["symbol"]),
                "trade_date": str(r["date"]),
                "side": str(r["side"]),
                "trade_type": "CASH",
                "currency": "TWD",
                "quantity": str(r["qty"]),
                "unit_price": str(r["price"]),
                "gross_amount": str(r["gross"]),
                "commission": str(r["commission"]),
                "tax": str(r["tax"]),
                "interest": "0",
                "net_settlement": str(r["net"]),
            }
        )
    return out


# 迷你合成：買 100 → 賣 100（STANDARD_FIFO）
_MINI_ROWS: list[dict[str, str | int]] = [
    {
        "symbol": "2236",
        "name": "合成",
        "date": "2024/08/05",
        "side": "BUY",
        "price": "10",
        "qty": 100,
        "gross": "1000",
        "commission": "1",
        "tax": "0",
        "net": "-1001",
    },
    {
        "symbol": "2236",
        "name": "合成",
        "date": "2024/08/08",
        "side": "SELL",
        "price": "11",
        "qty": 100,
        "gross": "1100",
        "commission": "1",
        "tax": "3",
        "net": "1096",
    },
]


def test_phase3_synthetic_c_matches_d_pipeline(tmp_path: Path) -> None:
    """合成 HTML → 正式 Import／FIFO／Report 須與獨立 C 一致。"""
    expected_c = build_expected_c_document(
        case_id="GOLD-SYN-PHASE3",
        source_sha256="a" * 64,
        source_path="synthetic/phase3.html",
        source_format="html_table_xls",
        applicable_spec=["docs/spec/SPEC.md §6", "docs/spec/SPEC.md §7"],
        rows=_rows_for_c(_MINI_ROWS),
        opening_lots_policy="NONE_APPROVED",
        expected_source_sha256={"syn": "a" * 64},
        actual_source_sha256={"syn": "a" * 64},
        invalid_row_count=0,
    )
    assert expected_c["validation_status"] in {
        "INDEPENDENTLY_COMPUTED",
        "INDEPENDENTLY_COMPUTED_PARTIAL",
    }

    html = _write_html(tmp_path / "syn.xls", _MINI_ROWS)
    db = tmp_path / "phase3.db"
    engine = init_db(db)
    Session = make_session_factory(engine)
    with Session() as session:
        pipe = run_import_match_report(
            session,
            source_path=html,
            broker_name="群益",
            account_label="phase3_syn",
            profile_id="statement_html_v1",
            out_dir=tmp_path / "out",
        )
        session.commit()
        actual = pipe["actual_d"]
        assert actual.get("open_cost_status") in {"VERIFIED_ZERO", "VERIFIED"}
        # 禁止把 expected_c open_cost 寫入 actual_d
        assert "open_cost_status" in actual
        result = compare_expected_c_to_actual_d(expected_c, actual)
        assert result["ok"] is True, result
        assert pipe["artifacts"]["ok"] is True, pipe["artifacts"]
        # 不得改寫 C
        assert expected_c["case_id"] == "GOLD-SYN-PHASE3"


def test_phase3_fault_injection_on_copy_fails_compare(tmp_path: Path) -> None:
    """先確認合法 D 與 C 一致，再複製竄改成本／收入 → compare FAIL。"""
    expected_c = build_expected_c_document(
        case_id="GOLD-SYN-PHASE3-FAULT",
        source_sha256="b" * 64,
        source_path="synthetic/phase3_fault.html",
        source_format="html_table_xls",
        applicable_spec=["docs/spec/SPEC.md §6"],
        rows=_rows_for_c(_MINI_ROWS),
        opening_lots_policy="NONE_APPROVED",
        expected_source_sha256={"syn": "b" * 64},
        actual_source_sha256={"syn": "b" * 64},
        invalid_row_count=0,
    )
    html = _write_html(tmp_path / "syn.xls", _MINI_ROWS)
    engine = init_db(tmp_path / "fault.db")
    Session = make_session_factory(engine)
    with Session() as session:
        pipe = run_import_match_report(
            session,
            source_path=html,
            broker_name="群益",
            account_label="phase3_fault",
            profile_id="statement_html_v1",
            out_dir=tmp_path / "out",
        )
        session.commit()
        actual = dict(pipe["actual_d"])
        assert compare_expected_c_to_actual_d(expected_c, actual)["ok"] is True

        mutated = dict(actual)
        mutated["cost"] = actual["cost"] + Decimal(1)
        mutated["income"] = actual["income"] + Decimal(1)
        bad = compare_expected_c_to_actual_d(expected_c, mutated)
        assert bad["ok"] is False
        assert "cost" in bad["diffs"] or "income" in bad["diffs"]
