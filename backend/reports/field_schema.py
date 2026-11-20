"""明細報表 A～W 欄位契約。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FieldKind = Literal["date", "text", "int", "number", "ratio", "emptyable_date", "emptyable_number", "emptyable_int", "emptyable_ratio"]


@dataclass(frozen=True)
class FieldDef:
    excel_col: str
    header: str
    kind: FieldKind


DETAIL_FIELDS: list[FieldDef] = [
    FieldDef("A", "買入日期", "date"),
    FieldDef("B", "賣出日期", "emptyable_date"),
    FieldDef("C", "股票代號", "text"),
    FieldDef("D", "商品名稱", "text"),
    FieldDef("E", "類別", "text"),
    FieldDef("F", "買價", "number"),
    FieldDef("G", "股數（買）", "int"),
    FieldDef("H", "手續費（買）", "number"),
    FieldDef("I", "賣價", "emptyable_number"),
    FieldDef("J", "股數（賣）", "emptyable_int"),
    FieldDef("K", "手續費（賣）", "emptyable_number"),
    FieldDef("L", "交易稅", "emptyable_number"),
    FieldDef("M", "利息", "emptyable_number"),
    FieldDef("N", "融資金額", "emptyable_number"),
    FieldDef("O", "融資年息", "emptyable_number"),
    FieldDef("P", "成本", "number"),
    FieldDef("Q", "收入", "emptyable_number"),
    FieldDef("R", "損益", "emptyable_number"),
    FieldDef("S", "獲利率", "emptyable_ratio"),
    FieldDef("T", "實際報酬率", "emptyable_ratio"),
    FieldDef("U", "券商", "text"),
    FieldDef("V", "大盤連動性", "emptyable_number"),
    FieldDef("W", "備註", "text"),
]

HEADERS = [f.header for f in DETAIL_FIELDS]
