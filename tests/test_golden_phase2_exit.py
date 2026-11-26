"""Phase 2 來源完整性 FAIL／BLOCKED 不得回傳成功結束碼。

SOURCE: SYNTHETIC_UNIT／FAULT_INJECTION — 結束碼契約。
"""

from __future__ import annotations


def test_phase2_exit_code_pass_when_all_complete() -> None:
    from scripts._golden_phase2_expected_c import phase2_exit_code

    cases = {
        "GOLD-001": {
            "validation_status": "INDEPENDENTLY_COMPUTED",
            "source_integrity": "PASS",
        },
        "GOLD-001-2236": {
            "validation_status": "INDEPENDENTLY_COMPUTED",
            "source_integrity": "PASS",
        },
    }
    assert phase2_exit_code(cases) == 0


def test_phase2_exit_code_nonzero_on_blocked_source_integrity() -> None:
    from scripts._golden_phase2_expected_c import phase2_exit_code

    cases = {
        "GOLD-001": {
            "validation_status": "BLOCKED_SOURCE_INTEGRITY",
            "source_integrity": "FAIL",
        }
    }
    assert phase2_exit_code(cases) == 1


def test_phase2_exit_code_nonzero_on_source_integrity_fail() -> None:
    from scripts._golden_phase2_expected_c import phase2_exit_code

    cases = {
        "GOLD-X": {
            "validation_status": "INDEPENDENTLY_COMPUTED",
            "source_integrity": "FAIL",
        }
    }
    assert phase2_exit_code(cases) == 1


def test_phase2_exit_code_allows_partial_without_fail() -> None:
    """PARTIAL（缺期初／UNKNOWN invalid）可非完整成功，但非 BLOCKED／FAIL → exit 0。"""
    from scripts._golden_phase2_expected_c import phase2_exit_code

    cases = {
        "GOLD-002": {
            "validation_status": "INDEPENDENTLY_COMPUTED_PARTIAL",
            "source_integrity": "PARTIAL",
        }
    }
    assert phase2_exit_code(cases) == 0


def test_phase2_full_acceptance_requires_source_lock_evidence() -> None:
    """缺少來源鎖定證據不得標記完整驗收成功。"""
    from scripts._golden_phase2_expected_c import may_mark_full_acceptance

    assert (
        may_mark_full_acceptance(
            validation_status="INDEPENDENTLY_COMPUTED",
            source_integrity="PASS",
            has_source_lock_evidence=True,
        )
        is True
    )
    assert (
        may_mark_full_acceptance(
            validation_status="INDEPENDENTLY_COMPUTED",
            source_integrity="PASS",
            has_source_lock_evidence=False,
        )
        is False
    )
    assert (
        may_mark_full_acceptance(
            validation_status="BLOCKED_SOURCE_INTEGRITY",
            source_integrity="FAIL",
            has_source_lock_evidence=True,
        )
        is False
    )
