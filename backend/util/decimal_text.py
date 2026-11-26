"""金額／單價文字正規化（匿名可比對；不涉及帳戶或憑證）。"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


def normalize_decimal_text(text: str) -> str:
    """將金額／單價字串正規化為可逐欄比對的文字。

    規則：
    - 去除千分位逗號與兩端空白
    - 以 ``Decimal`` 解析後輸出固定小數文字，並去掉尾隨 ``0``
      （例如 ``1105.00`` → ``1105``；``-4,424.50`` → ``-4424.5``）
    - 空字串維持空字串；無法解析則回傳去逗號後的原文字

    Args:
        text: 來源欄位文字（可含千分位）。

    Returns:
        正規化後的可比對字串。
    """
    raw = text.replace(",", "").strip()
    if raw == "":
        return ""
    try:
        rendered = format(Decimal(raw), "f")
        if "." in rendered:
            rendered = rendered.rstrip("0").rstrip(".")
        if rendered in {"", "-"}:
            return "0"
        return rendered
    except InvalidOperation:
        return raw
