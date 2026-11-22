"""端到端：匯入 → FIFO → 報表。"""

from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

from backend.db.repositories import find_account_by_label
from backend.domain.exceptions import BlockingExceptionError
from backend.services.allocation_service import match_fifo_for_account
from backend.services.import_service import apply_import
from backend.services.report_service import generate_detail_report


def test_e2e_sample_with_partial_report(db_session, fixtures_dir: Path, tmp_path: Path) -> None:
    src = fixtures_dir / "statement_sample.html"
    path = tmp_path / "sample.xls"
    path.write_bytes(src.read_bytes())

    result = apply_import(db_session, path, "群益", "main", "statement_html_v1")
    db_session.commit()
    assert result.trade_count == 5

    account = find_account_by_label(db_session, "main")
    assert account is not None
    _run, match = match_fifo_for_account(db_session, account.id)
    db_session.commit()
    assert match.blocking  # 合成甲 9991 早賣無買
    assert any(i.issue_code == "INSUFFICIENT_PRIOR_BUYS" for i in match.issues)

    out = tmp_path / "out"
    try:
        generate_detail_report(db_session, account.id, out, allow_partial=False)
        raised = False
    except BlockingExceptionError:
        raised = True
    assert raised

    xlsx, audit, exc = generate_detail_report(
        db_session, account.id, out, allow_partial=True
    )
    db_session.commit()
    assert "DRAFT" in xlsx.name
    assert audit.exists()
    assert exc.exists()

    wb = load_workbook(xlsx)
    ws = wb.active
    assert ws.max_row >= 2
    # 無合計
    for r in range(1, (ws.max_row or 1) + 1):
        for c in range(1, 24):
            val = ws.cell(r, c).value
            if isinstance(val, str):
                assert "總合" not in val


def test_e2e_fee_fixture_clean(db_session, fixtures_dir: Path, tmp_path: Path) -> None:
    src = fixtures_dir / "fifo_fee.html"
    path = tmp_path / "fee.xls"
    path.write_bytes(src.read_bytes())
    apply_import(db_session, path, "測試券商", "main", "statement_html_v1")
    db_session.commit()
    account = find_account_by_label(db_session, "main")
    assert account is not None
    _run, match = match_fifo_for_account(db_session, account.id)
    db_session.commit()
    assert not match.blocking
    assert sum(a.quantity for a in match.allocations) == 1200

    xlsx, _, _ = generate_detail_report(db_session, account.id, tmp_path / "out")
    db_session.commit()
    assert "DRAFT" not in xlsx.name
    wb = load_workbook(xlsx)
    ws = wb.active
    # 1 header + 3 rows (1000 matched, 200 matched, 300 unsold)
    assert ws.max_row == 4
