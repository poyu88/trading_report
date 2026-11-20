"""領域與流程例外。"""

from __future__ import annotations


class TradingReportError(Exception):
    """系統基底例外。"""


class FileFormatError(TradingReportError):
    """無法辨識或解析來源檔。"""


class ProfileError(TradingReportError):
    """Mapping profile 錯誤。"""


class ValidationError(TradingReportError):
    """交易驗證失敗。"""


class BlockingExceptionError(TradingReportError):
    """存在阻擋性例外，無法產生正式報表。"""


class DuplicateImportError(TradingReportError):
    """同帳戶同檔重複匯入。"""
