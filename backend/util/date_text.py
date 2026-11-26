"""交易日期文字解析（Manifest date_from／date_to；匿名可比對）。"""

from __future__ import annotations

from datetime import date, datetime


def parse_flexible_date(text: str) -> date | None:
    """解析常見券商日期字串（``YYYY/M/D``、``YYYY-MM-DD`` 等）。

    Args:
        text: 日期文字。

    Returns:
        ``date``；空白或無法解析 → ``None``（不臆造）。
    """
    raw = text.strip().replace(".", "/")
    if not raw:
        return None
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def date_bounds(texts: list[str]) -> tuple[date | None, date | None]:
    """以真實日期取最早／最晚；不得使用字串 lexicographic min／max。

    Args:
        texts: 日期字串清單。

    Returns:
        ``(date_from, date_to)``；無有效日期 → ``(None, None)``。
    """
    parsed = [d for d in (parse_flexible_date(t) for t in texts) if d is not None]
    if not parsed:
        return None, None
    return min(parsed), max(parsed)


def format_manifest_date(d: date | None) -> str:
    """Manifest 用日期字串；未知為 ``UNKNOWN``。"""
    if d is None:
        return "UNKNOWN"
    return f"{d.year}/{d.month}/{d.day}"
