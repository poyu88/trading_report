"""合成玉山 XLSX 測資（不得使用真實對帳單）。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from openpyxl import Workbook


HEADERS = [
    "交易類別",
    "股票名稱",
    "成交股數",
    "成交單價",
    "成交價金",
    "手續費",
    "交易稅",
    "自備款/保證金",
    "融資金/擔保金",
    "融券費",
    "利息",
    "淨收付金額",
    "損益",
    "報酬率(%)",
]


def write_synthetic_esun_xlsx(path: Path) -> Path:
    """產生涵蓋日期繼承、次列代號、四類型、小計與頁尾核對的合成檔。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "工作表1"

    # 前置說明列（表頭不在第 1 列）
    ws.append(["帳號：", "", "", "", "", "", "", "", "", "", "", "", "", ""])
    ws.append(["範圍：", "", "", "", "", "", "", "", "", "", "", "", "", ""])
    ws.append(["", "", "", "", "", "", "", "", "", "", "", "", "", ""])
    ws.append(HEADERS)

    # 2025-01-09：兩筆現股買進
    ws.append([date(2025, 1, 9)])
    ws.append(["現股買進", "ＩＥＴ–", 1000, 89.0, 89000, 126, 0, 0, 0, 0, 0, -89126, 0, 0])
    ws.append(["", -4971])
    ws.append(["現股買進", "精確", 1000, 40.95, 40950, 58, 0, 0, 0, 0, 0, -41008, 0, 0])
    ws.append(["", -3162])
    ws.append(["2025/01/09 小計", "", "", "", "", "", "", "", "", "", "", -130134])

    # 2025-02-25：現沖一賣一買
    ws.append([date(2025, 2, 25)])
    ws.append(["現沖賣出", "精確", 1000, 52.4, 52400, 74, 78, 0, 0, 0, 0, 52248, 0, 0])
    ws.append(["", -3162])
    ws.append(["現沖買進", "精確", 1000, 50.5, 50500, 71, 0, 0, 0, 0, 0, -50571, 0, 0])
    ws.append(["", -3162])
    ws.append(["2025/02/25 小計", "", "", "", "", "", "", "", "", "", "", 1677])

    # 2025-03-01：現股賣出
    ws.append([date(2025, 3, 1)])
    ws.append(["現股賣出", "ＩＥＴ–", 300, 113.5, 34050, 48, 102, 0, 0, 0, 0, 33900, 0, 0])
    ws.append(["", -4971])
    ws.append(["2025/03/01 小計", "", "", "", "", "", "", "", "", "", "", 33900])

    # 頁尾核對列
    # 成交：現股買2 + 現沖賣1 + 現沖買1 + 現股賣1 = 5
    # 價金：89000+40950+52400+50500+34050 = 266900
    # 手續費：126+58+74+71+48 = 377
    # 交易稅：0+0+78+0+102 = 180
    ws.append([])
    ws.append(
        [
            "資料筆數",
            "5筆",
            "成交價金",
            266900,
            "手續費",
            377,
            "交易稅",
            180,
            "淨收付金額",
            -94557,
        ]
    )
    ws.append([])
    ws.append(["說明："])
    ws.append(["本功能提供近三年的對帳單資訊，每次查詢區間最多12個月。"])

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def write_esun_missing_symbol_row(path: Path) -> Path:
    """成交列後缺少代號列 → 應列驗證錯誤。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "工作表1"
    ws.append(HEADERS)
    ws.append([date(2025, 1, 9)])
    ws.append(["現股買進", "精確", 1000, 40.0, 40000, 50, 0, 0, 0, 0, 0, -40050, 0, 0])
    # 故意不接下代號列，直接小計
    ws.append(["2025/01/09 小計", "", "", "", "", "", "", "", "", "", "", -40050])
    wb.save(path)
    return path


def write_esun_trade_without_date(path: Path) -> Path:
    """成交列出現在任何日期列之前 → 應列驗證錯誤。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "工作表1"
    ws.append(HEADERS)
    ws.append(["現股買進", "精確", 1000, 40.0, 40000, 50, 0, 0, 0, 0, 0, -40050, 0, 0])
    ws.append(["", -3162])
    wb.save(path)
    return path


def write_esun_with_unsupported_trade_type(path: Path) -> Path:
    """含融資買進（未支援）與一筆現股買進 → 未支援列應成例外，現股仍可辨識。

    Cloud Agent `esun_unsupported_rows_v1` RED 原始 fixture（僅融資）。
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "工作表1"
    ws.append(HEADERS)
    ws.append([date(2025, 1, 9)])
    ws.append(["融資買進", "精確", 1000, 40.0, 40000, 50, 0, 0, 0, 0, 0, -40050, 0, 0])
    ws.append(["", -3162])
    ws.append(["現股買進", "精確", 500, 41.0, 20500, 30, 0, 0, 0, 0, 0, -20530, 0, 0])
    ws.append(["", -3162])
    ws.append(["2025/01/09 小計", "", "", "", "", "", "", "", "", "", "", -60580])
    wb.save(path)
    return path


def write_esun_with_unsupported_trade_types(path: Path) -> Path:
    """含融資／配股等未支援類型：應進例外，不得靜默消失。

    本機補充 fixture：頁尾宣告含未支援列筆數／金額，供驗證
    「來源候選列 ≠ 來源核對 recognized」——未支援不計入 recognized_*。
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "工作表1"
    ws.append(HEADERS)

    ws.append([date(2025, 4, 10)])
    ws.append(["現股買進", "精確", 1000, 40.0, 40000, 50, 0, 0, 0, 0, 0, -40050, 0, 0])
    ws.append(["", -3162])
    ws.append(["融資買進", "精確", 1000, 41.0, 41000, 58, 0, 0, 10000, 0, 0, -31058, 0, 0])
    ws.append(["", -3162])
    ws.append(["配股", "精確", 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    ws.append(["", -3162])
    ws.append(["2025/04/10 小計", "", "", "", "", "", "", "", "", "", "", -71108])

    ws.append([])
    ws.append(
        [
            "資料筆數",
            "3筆",
            "成交價金",
            81000,
            "手續費",
            108,
            "交易稅",
            0,
            "淨收付金額",
            -71108,
        ]
    )
    ws.append([])
    ws.append(["說明："])
    ws.append(["本功能提供近三年的對帳單資訊，每次查詢區間最多12個月。"])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
