"""GOLD-TRUNC-NEG：受測 report_finance 正負數皆朝零截斷。

SOURCE: SYNTHETIC_UNIT — 純函式；無交易資料。
"""

from __future__ import annotations

from decimal import Decimal

from backend.services.report_finance import trunc_toward_zero


def test_trunc_toward_zero_positive_preserved() -> None:
    """既有正數語意：朝零（ROUND_DOWN）。"""
    assert trunc_toward_zero(Decimal("1.9")) == Decimal(1)
    assert trunc_toward_zero(Decimal("0.1")) == Decimal(0)
    assert trunc_toward_zero(Decimal("64.8") * 272) == Decimal(17625)


def test_trunc_toward_zero_negative_toward_zero() -> None:
    """負數亦朝零：-1.9 → -1（不得離零成 -2）。"""
    assert trunc_toward_zero(Decimal("-1.9")) == Decimal(-1)
    assert trunc_toward_zero(Decimal("-0.1")) == Decimal(0)
    assert trunc_toward_zero(Decimal("-64.8") * 1) == Decimal(-64)
