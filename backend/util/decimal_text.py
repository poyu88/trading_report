"""金額／單價文字正規化（匿名可比對；不涉及帳戶或憑證）。"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

# 整數部合法千分位：1–3 位起頭，其後僅允許 ,XXX 重覆；無逗號時為純數字。
_INT_WITH_GROUP = re.compile(r"^\d{1,3}(,\d{3})+$")
_INT_PLAIN = re.compile(r"^\d+$")


def _strip_valid_thousands(unsigned: str) -> str:
    """驗證千分位後移除逗號；非法格式 → ValueError。"""
    if "," not in unsigned:
        return unsigned
    if unsigned.count(".") > 1:
        raise ValueError(f"invalid_decimal:{unsigned!r}")
    if "." in unsigned:
        int_part, frac_part = unsigned.split(".", 1)
        if "," in frac_part:
            raise ValueError(f"invalid_decimal:{unsigned!r}")
    else:
        int_part, frac_part = unsigned, None
    if int_part == "" or not (
        _INT_WITH_GROUP.fullmatch(int_part) or _INT_PLAIN.fullmatch(int_part)
    ):
        raise ValueError(f"invalid_decimal:{unsigned!r}")
    # 有逗號時必須符合分組（純數字路徑不含逗號，此處必為 grouped）
    if "," in int_part and not _INT_WITH_GROUP.fullmatch(int_part):
        raise ValueError(f"invalid_decimal:{unsigned!r}")
    cleaned = int_part.replace(",", "")
    if frac_part is None:
        return cleaned
    return f"{cleaned}.{frac_part}"


def normalize_decimal_text(text: str) -> str:
    """將金額／單價字串正規化為可逐欄比對的文字。

    規則：
    - 空白與 ``0`` 有別：``""`` → ``""``；``0``／``-0`` → ``0``
    - 先驗證合法千分位再去逗號（``1,105`` OK；``11,05``／``1,,105``／``,`` 拒絕）
    - 允許前導 ``+``；正負零一律 ``0``
    - ``Decimal.is_finite()``：拒絕 NaN／Infinity／-Infinity
    - 無法解析或非有限 → ``ValueError``（不得回傳原文或固定 sentinel）

    Args:
        text: 來源欄位文字（可含千分位）。

    Returns:
        正規化後的可比對字串。

    Raises:
        ValueError: 非法數值（``invalid_decimal``）。
    """
    stripped = text.strip()
    if stripped == "":
        return ""

    sign = ""
    body = stripped
    if body.startswith("+"):
        body = body[1:].strip()
    elif body.startswith("-"):
        sign = "-"
        body = body[1:].strip()

    if body == "" or body == ",":
        raise ValueError(f"invalid_decimal:{text!r}")

    try:
        body = _strip_valid_thousands(body)
    except ValueError as exc:
        raise ValueError(f"invalid_decimal:{text!r}") from exc

    raw = f"{sign}{body}" if sign else body
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"invalid_decimal:{text!r}") from exc

    if not value.is_finite():
        raise ValueError(f"invalid_decimal:{text!r}")

    if value == 0:
        return "0"

    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    if rendered in {"", "-", "-0"}:
        return "0"
    return rendered


def decimal_texts_equal(left: str, right: str) -> bool:
    """兩邊皆可正規化且相等才為 True；任一方非法 → False（不得因相同非法字串而 True）。"""
    try:
        return normalize_decimal_text(left) == normalize_decimal_text(right)
    except ValueError:
        return False
