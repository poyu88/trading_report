"""CR-10：UAT ``build_uat_checks`` 不可假性通過（含反向失敗）。"""

from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.uat_fifo_same_day_2236 import build_uat_checks


def _passing_kwargs() -> dict:
    return {
        "required_outputs": {
            "detail_xlsx": True,
            "audit_json": True,
            "exceptions_csv": True,
            "fifo_trace": True,
            "conservation": True,
        },
        "migration_probe": {
            "day_trade_backfill_ok": True,
            "cash_standard_ok": True,
            "foreign_key_check_empty": True,
            "integrity_ok": True,
        },
        "fresh_schema_has_match_type": True,
        "allocated_qty": 4000,
        "qty_by_match_type": {"STANDARD_FIFO": 3600, "SAME_DAY_RECONCILED": 400},
        "unsold_qty": 0,
        "blocking": False,
        "conservation_ok": True,
        "audit_json": {
            "conservation_ok": True,
            "day_trade_annotation": {
                "status": "OK",
                "suspected_day_trade_qty": 1000,
                "same_day_reconciled_qty": 400,
                "warnings": [],
            },
        },
        "integrity_check_result": "ok",
        "h_annotation_non_interference": True,
        "detail_is_draft": False,
        "idempotent": {
            "old_run_preserved": True,
            "old_run_keys_unchanged": True,
            "new_run_keys_equal_old": True,
            "allocated_qty_same": True,
        },
        "formal_db_untouched": True,
        "run_dir_under_data_uat": True,
        "out_dir_under_output_uat": True,
        "detail_xlsx_finance_ok": True,
    }


def test_build_uat_checks_all_pass_on_normal_fixture() -> None:
    """正常 fixture → all(checks) True。"""
    checks = build_uat_checks(**_passing_kwargs())
    assert checks
    assert all(checks.values())


@pytest.mark.parametrize(
    "mutate,fail_key",
    [
        (lambda k: k["required_outputs"].__setitem__("fifo_trace", False), "required_fifo_trace"),
        (
            lambda k: k["required_outputs"].__setitem__("conservation", False),
            "required_conservation",
        ),
        (lambda k: k["required_outputs"].__setitem__("audit_json", False), "required_audit_json"),
        (lambda k: k["audit_json"].__setitem__("conservation_ok", False), "audit_json_conservation_ok"),
        (
            lambda k: k["audit_json"]["day_trade_annotation"].__setitem__("status", "FAILED"),
            "annotation_status_ok",
        ),
        (
            lambda k: k["audit_json"]["day_trade_annotation"].__setitem__(
                "suspected_day_trade_qty", 999
            ),
            "annotation_suspected_exact_1000",
        ),
        (
            lambda k: k["audit_json"]["day_trade_annotation"].__setitem__(
                "same_day_reconciled_qty", 0
            ),
            "annotation_reconciled_exact_400",
        ),
        (
            lambda k: k["audit_json"]["day_trade_annotation"].__setitem__(
                "warnings", ["ANNOTATION_FAILED:X"]
            ),
            "annotation_warnings_empty",
        ),
        (
            lambda k: k["migration_probe"].__setitem__("cash_standard_ok", False),
            "actual_migration_cash_standard_ok",
        ),
        (
            lambda k: k["migration_probe"].__setitem__("day_trade_backfill_ok", False),
            "actual_migration_day_trade_backfill",
        ),
        (lambda k: k.__setitem__("formal_db_untouched", False), "formal_db_untouched"),
        (
            lambda k: k["idempotent"].__setitem__("old_run_keys_unchanged", False),
            "idempotent_old_keys_unchanged",
        ),
        (lambda k: k.__setitem__("conservation_ok", False), "conservation_ok"),
        (lambda k: k.__setitem__("detail_is_draft", True), "not_draft"),
        (lambda k: k.__setitem__("blocking", True), "not_blocking"),
    ],
)
def test_build_uat_checks_reverse_failures(mutate, fail_key: str) -> None:
    """刻意注入失敗 → all(checks) 為 False，且對應鍵為 False。"""
    kwargs = deepcopy(_passing_kwargs())
    mutate(kwargs)
    checks = build_uat_checks(**kwargs)
    assert fail_key in checks
    assert checks[fail_key] is False
    assert all(checks.values()) is False


def test_build_uat_checks_missing_required_outputs_empty_fails() -> None:
    """缺 required_outputs → 不可假性通過。"""
    kwargs = deepcopy(_passing_kwargs())
    kwargs["required_outputs"] = {}
    checks = build_uat_checks(**kwargs)
    assert checks["required_outputs_all"] is False
    assert all(checks.values()) is False
