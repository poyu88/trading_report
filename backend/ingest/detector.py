"""依內容簽章判斷實際檔案格式。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from backend.domain.exceptions import FileFormatError


class FileKind(str, Enum):
    OLE_XLS = "ole_xls"
    XLSX = "xlsx"
    HTML_TABLE = "html_table"
    CSV = "csv"


OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP_MAGIC = b"PK\x03\x04"
MAX_FILE_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class DetectedFile:
    path: Path
    kind: FileKind
    encoding: str | None = None


def _looks_like_xlsx(data: bytes) -> bool:
    if not data.startswith(ZIP_MAGIC):
        return False
    # 粗略檢查 zip 內是否含 workbook 路徑字樣
    return b"xl/" in data or b"[Content_Types].xml" in data


def _try_decode(data: bytes, encodings: list[str]) -> str | None:
    for enc in encodings:
        try:
            text = data.decode(enc)
        except UnicodeDecodeError:
            continue
        if "\ufffd" in text:
            continue
        return enc
    return None


def detect_file(path: Path) -> DetectedFile:
    if not path.is_file():
        raise FileFormatError(f"檔案不存在：{path}")
    size = path.stat().st_size
    if size <= 0:
        raise FileFormatError("檔案為空")
    if size > MAX_FILE_BYTES:
        raise FileFormatError(f"檔案過大（>{MAX_FILE_BYTES} bytes），拒絕載入")

    data = path.read_bytes()
    if data.startswith(OLE_MAGIC):
        return DetectedFile(path=path, kind=FileKind.OLE_XLS)
    if _looks_like_xlsx(data):
        return DetectedFile(path=path, kind=FileKind.XLSX)

    # HTML 偽 XLS / CSV：嘗試解碼
    encodings = ["utf-8-sig", "utf-8", "cp950", "big5"]
    encoding = _try_decode(data, encodings)
    if encoding is None:
        raise FileFormatError("無法以已知編碼解碼檔案，請指定編碼")

    text = data.decode(encoding)
    lowered = text.lstrip().lower()
    if "<table" in lowered and "</table>" in lowered:
        return DetectedFile(path=path, kind=FileKind.HTML_TABLE, encoding=encoding)

    # CSV 啟發式：至少一行含逗號或 Tab
    first_lines = [ln for ln in text.splitlines() if ln.strip()][:5]
    if first_lines and any("," in ln or "\t" in ln for ln in first_lines):
        return DetectedFile(path=path, kind=FileKind.CSV, encoding=encoding)

    raise FileFormatError("無法辨識檔案格式（非 OLE XLS / XLSX / HTML table / CSV）")
