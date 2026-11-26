"""金額／單價文字正規化（匿名可比對；不涉及帳戶或憑證）。"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


def normalize_decimal_text(text: str) -> str:
    """將金額／單價字串正規化為可逐欄比對的文字。

    規則：
    - 去除千分位逗號與兩端空白；允許前導 ``+``
    - 以 ``Decimal`` 解析後輸出固定小數文字，並去掉尾隨 ``0``
      （例如 ``1105.00`` → ``1105``；``-4,424.50`` → ``-4424.5``）
    - 正負零一律為 ``0``（``-0``／``-0.00`` → ``0``）
    - 空字串維持空字串
    - 無法解析 → ``ValueError``（GOLD-CR-06 fail-closed；不得回傳原文字冒充可比對）

    Args:
        text: 來源欄位文字（可含千分位）。

    Returns:
        正規化後的可比對字串。

    Raises:
        ValueError: 非法數值（``invalid_decimal``）。
    """
    raw = text.replace(",", "").strip()
    if raw == "":
        return ""
    if raw.startswith("+"):
        raw = raw[1:].strip()
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"invalid_decimal:{text!r}") from exc

    if value == 0:
        return "0"

    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    if rendered in {"", "-", "-0"}:
        return "0"
    return rendered
