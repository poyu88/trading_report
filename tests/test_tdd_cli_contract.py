"""trading_report public-CLI contract tests (synthetic data only).

Run:
    uv run pytest tests/test_tdd_cli_contract.py -q -x

Black-box acceptance contracts based on docs/prd/PRD.md, docs/spec/SPEC.md, and
README CLI. Policy: docs/test/TDD.md. Current suite status: docs/test/TDD_STATUS.md
(characterization / regression baseline at commit cf4e68e; not historical TDD).

If the implementation uses a different import profile or output convention,
adapt fixtures/CLI wiring — do not weaken business assertions.

Every test uses pytest's temporary directory, never data/trading.db or real input.
"""

from __future__ import annotations

import hashlib
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from decimal import Decimal
from html import escape
from pathlib import Path

import pytest
from openpyxl import load_workbook

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROFILE = "statement_html_v1"
ACCOUNT = "tdd-demo"
BROKER = "合成測試券商"

HEADERS = [
    "商品", "成交日", "買賣別", "幣別", "成交價", "成交股數",
    "成交金額", "手續費", "交易稅", "淨收付", "融資金額/ 擔保價款",
    "自備款/ 保證金", "利息", "融券 手續費", "標借費",
    "證所稅", "健保費", "下單來源別",
]


@dataclass(frozen=True)
class DemoTrade:
    date: str
    side: str                         # BUY / SELL
    qty: int
    price: str
    commission: str = "0"
    tax: str = "0"
    symbol: str = "0050"            # deliberately starts with a zero
    name: str = "測試股票"


def make_html_xls(path: Path, trades: list[DemoTrade], *, summary: bool = False) -> Path:
    """Create a synthetic broker HTML table with an .xls extension."""
    def td(s: str) -> str:
        return f"<td>{escape(s)}</td>"

    chunks = ["<html><meta charset='UTF-8'><body><table border='2px'>"]
    chunks.append("<tr>" + "".join(td(h) for h in HEADERS) + "</tr>")

    for t in trades:
        amount = Decimal(t.price) * t.qty
        fee = Decimal(t.commission)
        tax = Decimal(t.tax)
        settlement = -amount - fee - tax if t.side == "BUY" else amount - fee - tax
        stock_cell = (
            f'<td><span class="stockCode">{escape(t.symbol)}</span> '
            f'<span class="stockName">{escape(t.name)}</span></td>'
        )
        rest = [
            t.date, "現股買進" if t.side == "BUY" else "現股賣出",
            "臺幣", t.price, str(t.qty), str(amount),
            t.commission, t.tax, str(settlement),
            "0", "0", "0", "0", "0", "0", "0", "TDD 測試",
        ]
        chunks.append("<tr>" + stock_cell + "".join(td(x) for x in rest) + "</tr>")

    if summary:
        # A summary row must never become a canonical BUY / SELL trade.
        chunks.append("<tr>" + td("總合(測試)") + "".join(td("") for _ in range(17)) + "</tr>")

    chunks.append("</table></body></html>")
    path.write_text("".join(chunks), encoding="utf-8")
    return path


@pytest.fixture
def env(tmp_path: Path):
    """Isolated DB, input and output for each case: never touch production."""
    source_dir = tmp_path / "input"
    source_dir.mkdir()
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    db_path = tmp_path / "trading.db"

    def cli(*parts: object, ok: bool = True) -> subprocess.CompletedProcess[str]:
        cmd = [sys.executable, "-m", "backend.cli", *(str(p) for p in parts)]
        result = subprocess.run(
            cmd, cwd=PROJECT_ROOT, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=60,
            check=False,  # 契約測自行 assert returncode；勿用 check=True 改寫失敗語意
        )
        if ok:
            assert result.returncode == 0, (
                f"CLI failed (exit={result.returncode})\n"
                f"cmd: {' '.join(cmd)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result

    cli("db", "init", "--db", db_path)
    return {"db": db_path, "input": source_dir, "output": out_dir, "cli": cli}


def apply(env, filename: str, trades: list[DemoTrade], *, account: str = ACCOUNT,
          summary: bool = False) -> Path:
    file = make_html_xls(env["input"] / filename, trades, summary=summary)
    env["cli"](
        "import", "apply", "--file", file,
        "--broker", BROKER, "--account", account,
        "--profile", PROFILE, "--db", env["db"],
    )
    return file


def match(env, *, account: str = ACCOUNT) -> None:
    env["cli"]("match", "fifo", "--account", account, "--db", env["db"])


def report(env, *, account: str = ACCOUNT, draft: bool = False) -> Path:
    parts = ["report", "detail", "--account", account,
             "--output-dir", env["output"], "--db", env["db"]]
    if draft:
        parts.append("--allow-partial")
    env["cli"](*parts)
    prefix = "交易明細_DRAFT_" if draft else "交易明細_"
    files = [p for p in env["output"].glob(f"{prefix}*.xlsx") if
             ("DRAFT" in p.name) == draft]
    assert files, f"Could not find expected {'DRAFT' if draft else 'final'} .xlsx in {env['output']}"
    return max(files, key=lambda p: p.stat().st_mtime_ns)


def scalar(db_path: Path, sql: str, parameters: tuple = ()) -> int:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(sql, parameters).fetchone()[0]


def detail_rows(xlsx: Path):
    workbook = load_workbook(xlsx, data_only=False)
    sheet = workbook.active
    assert sheet.max_column == 23, f"Expected A:W (23 columns), got {sheet.max_column}"
    return sheet, list(sheet.iter_rows(min_row=2, max_col=23))


def cell_decimal(cell) -> Decimal:
    assert cell.data_type == "n", f"Expected numeric cell, got {cell.coordinate}: {cell.value!r}"
    return Decimal(str(cell.value))


# ── INGEST / DB: contract (regression baseline) ──────────────────────────

def test_01_preview_does_not_insert_trades(env):
    source = make_html_xls(env["input"] / "preview.xls", [
        DemoTrade("2026/01/05", "BUY", 100, "10"),
    ])
    env["cli"]("import", "preview", "--file", source,
               "--profile", PROFILE, "--db", env["db"])
    assert scalar(env["db"], "SELECT COUNT(*) FROM trades") == 0


def test_02_html_xls_is_normalized_and_summary_row_excluded(env):
    apply(env, "normal.xls", [
        DemoTrade("2026/01/05", "BUY", 100, "10.25"),
        DemoTrade("2026/01/06", "SELL", 40, "11.25"),
    ], summary=True)
    with sqlite3.connect(env["db"]) as conn:
        rows = conn.execute(
            "SELECT symbol, side, quantity FROM trades ORDER BY trade_date"
        ).fetchall()
    assert rows == [("0050", "BUY", 100), ("0050", "SELL", 40)]


def test_03_same_file_same_account_import_is_idempotent(env):
    file = apply(env, "duplicate.xls", [DemoTrade("2026/01/05", "BUY", 100, "10")])
    before = scalar(env["db"], "SELECT COUNT(*) FROM trades")
    env["cli"]("import", "apply", "--file", file, "--broker", BROKER,
               "--account", ACCOUNT, "--profile", PROFILE, "--db", env["db"])
    after = scalar(env["db"], "SELECT COUNT(*) FROM trades")
    assert (before, after) == (1, 1)


def test_04_identical_real_executions_are_not_collapsed(env):
    apply(env, "two_buys.xls", [
        DemoTrade("2026/01/05", "BUY", 100, "10"),
        DemoTrade("2026/01/05", "BUY", 100, "10"),
    ])
    assert scalar(env["db"], "SELECT COUNT(*) FROM trades WHERE side = 'BUY'") == 2


def test_05_source_is_unchanged_after_apply(env):
    source = make_html_xls(env["input"] / "source.xls", [
        DemoTrade("2026/01/05", "BUY", 100, "10")
    ])
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    env["cli"]("import", "apply", "--file", source, "--broker", BROKER,
               "--account", ACCOUNT, "--profile", PROFILE, "--db", env["db"])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


# ── FIFO / FEES / REPORT: contract exercised end-to-end ─────────────────

def test_06_fifo_one_sell_consumes_two_buys_and_preserves_fees(env):
    apply(env, "fifo.xls", [
        DemoTrade("2026/01/05", "BUY", 1000, "10", commission="20"),
        DemoTrade("2026/01/06", "BUY", 500, "11", commission="10"),
        DemoTrade("2026/01/07", "SELL", 1200, "12", commission="18", tax="36"),
    ])
    match(env)

    with sqlite3.connect(env["db"]) as conn:
        allocations = conn.execute(
            """SELECT b.quantity, a.allocated_quantity
               FROM fifo_allocations a JOIN trades b ON a.buy_trade_id = b.id
               ORDER BY b.trade_date"""
        ).fetchall()
    assert allocations == [(1000, 1000), (500, 200)]

    _sheet, rows = detail_rows(report(env))
    assert len(rows) == 3  # 2 sold segments + 1 open remainder
    assert sorted(int(r[6].value) for r in rows) == [200, 300, 1000]
    assert sum(cell_decimal(r[7]) for r in rows) == Decimal(30)        # H buy fees
    assert sum(cell_decimal(r[10]) for r in rows if r[10].value is not None) == Decimal(18)
    assert sum(cell_decimal(r[11]) for r in rows if r[11].value is not None) == Decimal(36)
    assert sorted(cell_decimal(r[7]) for r in rows) == [Decimal(0), Decimal(10), Decimal(20)]

    # Sold quantities balance; unsold is an actual numeric remainder, not text.
    assert sum(int(r[9].value) for r in rows if r[9].value is not None) == 1200
    unsold = [r for r in rows if r[9].value is None]
    assert len(unsold) == 1 and unsold[0][6].value == 300
    for index in (1, 8, 9, 10, 11, 16, 17, 18):  # B/I/J/K/L/Q/R/S
        assert unsold[0][index].value is None


def test_07_one_buy_split_by_two_sells_fee_occurs_once(env):
    apply(env, "two_sells.xls", [
        DemoTrade("2026/02/01", "BUY", 1000, "10", commission="20"),
        DemoTrade("2026/02/02", "SELL", 400, "12", commission="8", tax="14"),
        DemoTrade("2026/02/03", "SELL", 300, "13", commission="9", tax="15"),
    ])
    match(env)
    _, rows = detail_rows(report(env))
    assert sorted(int(r[6].value) for r in rows) == [300, 300, 400]
    assert sorted(cell_decimal(r[7]) for r in rows) == [Decimal(0), Decimal(0), Decimal(20)]
    assert sum(cell_decimal(r[10]) for r in rows if r[10].value is not None) == 17
    assert sum(cell_decimal(r[11]) for r in rows if r[11].value is not None) == 29


def test_08_report_has_only_23_typed_columns_and_no_total_or_formula(env):
    apply(env, "typed.xls", [
        DemoTrade("2026/01/05", "BUY", 100, "10.25"),
        DemoTrade("2026/01/06", "SELL", 40, "11.25", commission="2", tax="1"),
    ])
    match(env)
    sheet, rows = detail_rows(report(env))
    assert sheet.max_row == len(rows) + 1
    assert len(rows) == 2  # sold 40 + unsold 60
    assert sheet["C1"].value is not None
    assert all(r[2].value == "0050" and r[2].data_type == "s" for r in rows)
    assert all(r[0].is_date for r in rows)
    assert all(r[6].data_type == "n" for r in rows)
    assert all(c.data_type != "f" for row in sheet for c in row)
    forbidden = ("總合", "總計", "合計", "SUM(")
    assert all(
        not (isinstance(c.value, str) and any(x in c.value for x in forbidden))
        for row in rows for c in row
    )


def test_09_unmatched_earlier_sell_blocks_final_but_allows_draft(env):
    apply(env, "missing_opening.xls", [
        DemoTrade("2026/01/02", "SELL", 100, "12", commission="2", tax="4"),
        DemoTrade("2026/01/05", "BUY", 100, "10", commission="2"),
    ])
    match(env)
    final = env["cli"]("report", "detail", "--account", ACCOUNT,
                       "--output-dir", env["output"], "--db", env["db"], ok=False)
    assert final.returncode != 0, "Unmatched sell must block a FINAL report"
    assert not any(p.name.startswith("交易明細_") and "DRAFT" not in p.name
                   for p in env["output"].glob("交易明細_*.xlsx"))
    _, rows = detail_rows(report(env, draft=True))
    assert len(rows) == 1 and rows[0][9].value is None  # later BUY remains open
    issues = list(env["output"].glob("*_exceptions.csv"))
    assert issues, "DRAFT must emit exceptions CSV"
    assert "INSUFFICIENT_PRIOR_BUYS" in issues[-1].read_text(encoding="utf-8-sig")


def test_10_fifo_never_matches_buys_from_different_accounts(env):
    apply(env, "account_a.xls", [DemoTrade("2026/01/02", "BUY", 100, "10")],
          account="acct-a")
    apply(env, "account_b.xls", [DemoTrade("2026/01/03", "SELL", 100, "12")],
          account="acct-b")
    match(env, account="acct-b")
    result = env["cli"]("report", "detail", "--account", "acct-b",
                        "--output-dir", env["output"], "--db", env["db"], ok=False)
    assert result.returncode != 0, "Must not borrow lots from another account"


def test_11_second_report_must_not_overwrite_first(env):
    apply(env, "output_twice.xls", [DemoTrade("2026/01/05", "BUY", 100, "10")])
    match(env)
    first = report(env)
    first_bytes = first.read_bytes()
    second = report(env)
    assert first != second, "Each report run must produce a unique timestamped filename"
    assert first.read_bytes() == first_bytes


def test_12_backup_is_a_consistent_sqlite_database(env, tmp_path: Path):
    apply(env, "backup.xls", [DemoTrade("2026/01/05", "BUY", 100, "10")])
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    env["cli"]("db", "backup", "--output-dir", backup_dir, "--db", env["db"])
    backups = list(backup_dir.glob("*.db")) + list(backup_dir.glob("*.sqlite"))
    assert backups, f"No SQLite backup in {backup_dir}"
    with sqlite3.connect(backups[0]) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0] == 1
