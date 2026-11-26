"""來源指紋鎖定比對（GOLD-CR-08）。"""

from __future__ import annotations


def sha256_lock_mismatches(
    expected: dict[str, str],
    actual: dict[str, str],
) -> list[str]:
    """回傳 actual 與 expected 不一致的 key 清單（排序）。

    Args:
        expected: 鎖定的完整 64 字元 SHA256。
        actual: 盤點實際 SHA256。

    Returns:
        不一致之 key；缺 key 或值不同均計入。
    """
    bad: list[str] = []
    for key, exp in expected.items():
        got = actual.get(key)
        if got != exp:
            bad.append(key)
    return sorted(bad)


def assert_sha256_lock(expected: dict[str, str], actual: dict[str, str]) -> None:
    """不一致則 raise ``ValueError``（fail-closed）。"""
    bad = sha256_lock_mismatches(expected, actual)
    if bad:
        raise ValueError(f"sha256_lock_mismatch:{','.join(bad)}")
