"""交易驗證：價金一致性等。"""

from __future__ import annotations

from decimal import Decimal

from backend.ingest.mapping import MappingProfile
from backend.ingest.normalizer import NormalizedCandidate


def validate_gross_consistency(
    candidate: NormalizedCandidate,
    profile: MappingProfile,
) -> str | None:
    """檢查 成交價×股數 與 成交金額 差異；超出容許則回傳錯誤碼。"""
    if candidate.excluded or candidate.error_code:
        return candidate.error_code
    expected = candidate.unit_price * Decimal(candidate.quantity)
    tolerance = Decimal(profile.gross_tolerance)
    diff = abs(expected - candidate.gross_amount)
    if diff > tolerance:
        return "GROSS_AMOUNT_MISMATCH"
    return None
