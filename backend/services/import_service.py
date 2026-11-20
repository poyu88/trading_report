"""匯入預覽與入庫。"""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import SOURCE_ARCHIVE_DIR
from backend.db.models import ImportBatch, RawRow, TradeRow
from backend.db.repositories import find_batch_by_hash, get_or_create_account, get_or_create_broker
from backend.domain.exceptions import FileFormatError
from backend.domain.models import decimal_to_txt
from backend.ingest.csv_parser import parse_csv
from backend.ingest.detector import FileKind, detect_file
from backend.ingest.esun_xlsx_parser import parse_esun_xlsx
from backend.ingest.excel_parser import parse_excel
from backend.ingest.html_parser import ParsedTable, parse_html_table
from backend.ingest.mapping import MappingProfile, load_profile, map_row
from backend.ingest.normalizer import NormalizedCandidate, normalize_mapped_row
from backend.ingest.validator import validate_gross_consistency


@dataclass
class PreviewRow:
    row_index: int
    status: str
    symbol: str | None = None
    side: str | None = None
    quantity: int | None = None
    message: str | None = None


@dataclass
class ImportPreview:
    file_path: str
    file_kind: str
    file_sha256: str
    profile_id: str
    total_rows: int
    trade_count: int
    buy_count: int
    sell_count: int
    excluded_count: int
    error_count: int
    rows: list[PreviewRow]
    source_reconciliation: dict[str, Any] | None = None


@dataclass
class ImportResult:
    batch_id: str
    already_imported: bool
    trade_count: int
    excluded_count: int
    error_count: int
    message: str


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_with_profile(path: Path, profile: MappingProfile) -> tuple[ParsedTable, str]:
    detected = detect_file(path)
    if profile.source_format == "esun_xlsx":
        if detected.kind not in (FileKind.OLE_XLS, FileKind.XLSX):
            raise FileFormatError(
                f"esun_xlsx profile 需要真 Excel，實際為：{detected.kind.value}"
            )
        table = parse_esun_xlsx(path, profile)
        return table, detected.kind.value
    if detected.kind == FileKind.HTML_TABLE:
        table = parse_html_table(path, profile, encoding=detected.encoding or "utf-8")
    elif detected.kind == FileKind.CSV:
        table = parse_csv(path, profile, encoding=detected.encoding or "utf-8-sig")
    elif detected.kind in (FileKind.OLE_XLS, FileKind.XLSX):
        table = parse_excel(path, profile)
    else:
        raise FileFormatError(f"不支援的格式：{detected.kind}")
    return table, detected.kind.value


def _process_rows(
    table: ParsedTable,
    profile: MappingProfile,
) -> list[tuple[int, dict[str, str], NormalizedCandidate]]:
    results: list[tuple[int, dict[str, str], NormalizedCandidate]] = []
    for row_index, values in table.rows:
        original = {
            table.headers[i]: values[i] for i in range(len(table.headers))
        }
        mapped = map_row(table.headers, values, profile)
        candidate = normalize_mapped_row(mapped, profile, original)
        if not candidate.excluded and not candidate.error_code:
            mismatch = validate_gross_consistency(candidate, profile)
            if mismatch:
                candidate.error_code = mismatch
                candidate.error_message = (
                    f"成交金額與單價×股數差異過大："
                    f"{candidate.gross_amount} vs {candidate.unit_price * candidate.quantity}"
                )
        results.append((row_index, original, candidate))
    return results


def preview_import(path: Path, profile_id: str) -> ImportPreview:
    profile = load_profile(profile_id)
    file_hash = sha256_file(path)
    table, kind = _parse_with_profile(path, profile)
    processed = _process_rows(table, profile)

    preview_rows: list[PreviewRow] = []
    buy = sell = excluded = errors = trades = 0
    for row_index, _original, cand in processed:
        if cand.excluded:
            excluded += 1
            preview_rows.append(
                PreviewRow(row_index, "excluded", message=cand.exclude_reason)
            )
        elif cand.error_code:
            errors += 1
            preview_rows.append(
                PreviewRow(
                    row_index,
                    "error",
                    symbol=cand.symbol or None,
                    message=cand.error_message or cand.error_code,
                )
            )
        else:
            trades += 1
            if cand.side == "BUY":
                buy += 1
            else:
                sell += 1
            preview_rows.append(
                PreviewRow(
                    row_index,
                    "ok",
                    symbol=cand.symbol,
                    side=cand.side,
                    quantity=cand.quantity,
                )
            )

    return ImportPreview(
        file_path=str(path),
        file_kind=kind,
        file_sha256=file_hash,
        profile_id=profile.profile_id,
        total_rows=len(processed),
        trade_count=trades,
        buy_count=buy,
        sell_count=sell,
        excluded_count=excluded,
        error_count=errors,
        rows=preview_rows,
        source_reconciliation=table.source_reconciliation,
    )


def _archive_source(path: Path, file_hash: str) -> Path:
    SOURCE_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    dest = SOURCE_ARCHIVE_DIR / f"{file_hash}{path.suffix.lower()}"
    if not dest.exists():
        shutil.copy2(path, dest)
    return dest


def apply_import(
    session: Session,
    path: Path,
    broker_name: str,
    account_label: str,
    profile_id: str,
) -> ImportResult:
    profile = load_profile(profile_id)
    file_hash = sha256_file(path)
    table, _kind = _parse_with_profile(path, profile)

    broker_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"broker:{broker_name}"))
    account_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"account:{broker_name}:{account_label}"))
    broker = get_or_create_broker(session, broker_id, broker_name)
    account = get_or_create_account(session, account_id, broker.id, account_label)

    existing = find_batch_by_hash(
        session, account.id, file_hash, profile.profile_id, profile.version
    )
    if existing:
        trade_count = session.scalar(
            select(func.count())
            .select_from(TradeRow)
            .join(RawRow, TradeRow.raw_row_id == RawRow.id)
            .where(RawRow.batch_id == existing.id)
        ) or 0
        return ImportResult(
            batch_id=existing.id,
            already_imported=True,
            trade_count=trade_count,
            excluded_count=0,
            error_count=0,
            message="同帳戶同檔已匯入，未新增交易",
        )

    processed = _process_rows(table, profile)
    archive_path = _archive_source(path, file_hash)
    batch_id = str(uuid.uuid4())
    batch = ImportBatch(
        id=batch_id,
        account_id=account.id,
        file_sha256=file_hash,
        filename=path.name,
        profile_id=profile.profile_id,
        profile_version=profile.version,
        status="completed",
        archive_path=str(archive_path),
    )
    session.add(batch)

    trade_count = excluded_count = error_count = 0
    for row_index, original, cand in processed:
        raw_json = json.dumps(original, ensure_ascii=False)
        raw_id = str(uuid.uuid4())
        if cand.excluded:
            status = "excluded"
            error_code = "EXCLUDED"
            excluded_count += 1
        elif cand.error_code:
            status = "error"
            error_code = cand.error_code
            error_count += 1
        else:
            status = "ok"
            error_code = None
            trade_count += 1

        raw = RawRow(
            id=raw_id,
            batch_id=batch_id,
            sheet_name=table.sheet_name,
            row_index=row_index,
            raw_json=raw_json,
            row_sha256=sha256_text(raw_json),
            parse_status=status,
            error_code=error_code,
        )
        session.add(raw)

        if status == "ok":
            trade = TradeRow(
                id=str(uuid.uuid4()),
                raw_row_id=raw_id,
                account_id=account.id,
                symbol=cand.symbol,
                name=cand.name,
                trade_date=cand.trade_date.isoformat(),
                trade_time=None,
                trade_sequence=None,
                side=cand.side,
                trade_type=cand.trade_type,
                currency=cand.currency,
                quantity=cand.quantity,
                unit_price_txt=decimal_to_txt(cand.unit_price),
                gross_amount_txt=decimal_to_txt(cand.gross_amount),
                commission_txt=decimal_to_txt(cand.commission),
                tax_txt=decimal_to_txt(cand.tax),
                interest_txt=decimal_to_txt(cand.interest),
                net_settlement_txt=(
                    decimal_to_txt(cand.net_settlement) if cand.net_settlement is not None else None
                ),
                raw_payload_json=raw_json,
            )
            session.add(trade)

    session.flush()
    return ImportResult(
        batch_id=batch_id,
        already_imported=False,
        trade_count=trade_count,
        excluded_count=excluded_count,
        error_count=error_count,
        message=f"匯入完成：交易 {trade_count}、排除 {excluded_count}、錯誤 {error_count}",
    )


def preview_to_dict(preview: ImportPreview) -> dict[str, Any]:
    return {
        **{k: v for k, v in asdict(preview).items() if k != "rows"},
        "rows": [asdict(r) for r in preview.rows[:50]],
        "rows_truncated": len(preview.rows) > 50,
    }
