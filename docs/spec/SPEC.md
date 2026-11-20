# SPEC — 股票交易對帳單自動整理系統技術規格

> 專案：`trading_report`  
> 文件版本：v1.0（技術設計基準稿）  
> 文件日期：2026-11-20  
> 依據：同目錄 `PRD.md`、`Statement (2).xls`、`股票對帳單.xlsx`  
> 原則：**免費開源優先、離線可運作、可測試、最小修改原範本、資料可稽核**。

## 1. 技術架構

```text
CSV / 真 .xls / HTML 偽 .xls / .xlsx
              │
              ▼
     File Detector + Parsers
              │
              ▼
    Normalizer + Validator ──────> Exception Log
              │
              ▼
     Imported Trade Registry
              │
既有 Excel ────┼─────────────┐
              ▼             │
     Position Snapshot      │
              │             │
              ▼             │
       FIFO Matcher         │
              │             │
              ▼             ▼
        Trade Segments + Excel Writer
              │
              ▼
     Formula / Quantity / Fee Audit
              │
              ▼
      原範本保留、另存新版 XLSX
      + audit.json + exceptions.csv
```

### 1.1 設計原則

- **交易業務規則與 Excel 寫入分離**：FIFO 純 Python，不依賴 pandas、openpyxl 或 UI。
- **先驗證、後寫入、再驗證**：解析不合格、庫存負數、重複費用、公式損壞均不應產出「成功」報告。
- **先建立標準化交易資料模型**，再產生 Excel 列；不要直接在 Excel 上邊讀邊做 FIFO，避免插入列造成配對錯誤。
- **可重現**：交易排序、拆分及整數元尾差分配都需要固定規則及測試。
- **本機優先**：不需要 PostgreSQL、FastAPI、Docker、雲端服務或付費券商 API。

## 2. 免費技術棧與授權

| 層次 | 套件／工具 | 授權（常見公開授權） | V1 用途 | 必要性 |
| --- | --- | --- | --- | --- |
| Runtime | Python 3.11+ | PSF License | 主程式 | 必需 |
| Dependency manager | `uv` | MIT / Apache-2.0（依發行版） | 解析依賴、鎖定環境 | 必需 |
| Excel writer | `openpyxl` | MIT | 在既有 `.xlsx` 修改工作表／公式／樣式 | 必需 |
| Excel reader | `python-calamine` | MIT | 讀取真正的 `.xls`、`.xlsx`；僅讀不回寫 | 必需 |
| HTML reader | `beautifulsoup4` | MIT | 解析 HTML 偽裝 `.xls` | 必需 |
| CSV reader | Python `csv` | 標準函式庫 | 讀取 CSV、支援可設定編碼 | 必需 |
| Math | Python `decimal` | 標準函式庫 | 金額與捨入 | 必需 |
| FIFO queue | `collections.deque` | 標準函式庫 | 庫存批次先進先出 | 必需 |
| Models | `dataclasses` / `typing` | 標準函式庫 | 明確型別資料模型 | 必需 |
| CLI | `argparse` | 標準函式庫 | 本機命令列 | 必需 |
| Logging / hash | `logging` / `hashlib` / `json` | 標準函式庫 | 稽核、指紋及紀錄 | 必需 |
| Unit tests | `pytest` | MIT | 自動測試 | 必需（開發依賴） |
| Formatter / lint | `ruff` | MIT | 格式化／靜態分析 | 建議（開發依賴） |
| Tabular analysis | `pandas` | BSD-3-Clause | 複雜欄位清理／預覽；非 FIFO 必需 | 選用 |
| GUI | `streamlit` | Apache-2.0 | 第二階段本機介面 | P1 選用 |

> 套件免費不代表 Windows Microsoft Excel 本身免費。核心程式**不得依賴 Excel COM / `pywin32` 完成工作**；如日後需要 Excel 自動重算，可做成使用者自行選用的額外整合。套件版本與授權請在實作時以 lockfile 及隨附 LICENSE 重新核對。
>
> 官方參考：https://pypi.org/project/python-calamine/ 、https://pypi.org/project/openpyxl/ 、https://docs.astral.sh/uv/ 、https://docs.pytest.org/ 。

### 2.1 初始化（PowerShell／Cursor Terminal）

```powershell
# 若新專案尚無 pyproject.toml
uv init --python 3.11

# V1 執行依賴
uv add openpyxl python-calamine beautifulsoup4

# 開發、測試依賴
uv add --dev pytest ruff

# 檢查
uv run pytest
```

**不需要安裝**：付費 Office 套件、OpenAI API、雲端資料庫、前端 Node.js（第一階段）。本規格示範從專案根目錄執行 `python -m backend.cli`，因此 `backend/` 必須有 `__init__.py`，並採用套件內相對匯入。

## 3. 專案結構

```text
trading_report/
├── .cursor/
│   ├── BUGBOT.md
│   ├── hooks.json
│   └── rules/
│       ├── backend-rule.mdc
│       └── commit-rule.mdc
├── hooks/
│   ├── check_sensitive_file.py
│   └── check_sensitive_prompt.py
├── docs/
│   ├── PRD.md
│   ├── SPEC.md
│   └── TEST_PLAN.md                  # 後續由 Agent 撰寫
├── backend/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── detector.py
│   ├── domain.py
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── csv_reader.py
│   │   ├── excel_reader.py
│   │   └── html_xls_reader.py
│   ├── normalizer.py
│   ├── existing_positions.py
│   ├── fifo.py
│   ├── fee_policy.py
│   ├── excel_writer.py
│   ├── formula_guard.py
│   ├── reconciliation.py
│   └── audit.py
├── tests/
│   ├── fixtures/                    # 合成、去識別化測試資料
│   ├── test_detect_and_parse.py
│   ├── test_normalize.py
│   ├── test_fifo.py
│   ├── test_fees.py
│   ├── test_existing_positions.py
│   ├── test_excel_formula_guard.py
│   ├── test_idempotency.py
│   └── test_end_to_end.py
├── input/                             # 不納入 Git
├── output/                            # 不納入 Git
├── .state/                            # manifest 等，不納入 Git
├── pyproject.toml
├── uv.lock
├── .gitignore
└── README.md
```

> `uv.lock` 可納入版本管理；實際個人交易檔、輸出、憑證、匯入 manifest 不應提交到 Git。

## 4. 來源檔偵測與解析

### 4.1 Detectors

| 檔案實際格式 | 偵測 | 處理方式 |
| --- | --- | --- |
| CSV | 文字、分隔符、可解碼 | `csv` 模組 |
| HTML 偽 `.xls` | 前段文字有 `<table`、HTML 標記 | `beautifulsoup4` |
| OLE 二進位 `.xls` | 開頭魔術位元 `D0 CF 11 E0 A1 B1 1A E1` | `python-calamine` |
| `.xlsx` | ZIP signature，確認含 `xl/workbook.xml` | `python-calamine` 讀來源；`openpyxl` 讀寫彙整 |
| 非上述檔案 | 偵測不到或損壞 | 拒絕、列出檔案及原因 |

檔案大小設安全上限（預設例如 30 MB，可設定）。HTML 解析只擷取表格文字，不允許執行 JavaScript 或連外載入內容；CSV/Excel 讀取過程不執行巨集或公式。

### 4.2 已知 HTML 來源欄位映射

| 來源欄 | 標準欄位 | 註記 |
| --- | --- | --- |
| `商品` | `symbol`, `name` | 例如 `3260 威剛`；代號一律字串 |
| `成交日` | `trade_date` | 格式 `YYYY/MM/DD` |
| `買賣別` | `side`, `trade_type` | `現股買進`→BUY、`現股賣出`→SELL |
| `幣別` | `currency` | `臺幣`→TWD |
| `成交價` | `unit_price` | Decimal |
| `成交股數` | `quantity` | 正整數，允許零股數量 |
| `成交金額` | `gross_amount` | Decimal，不直接用 `price * qty` 覆蓋 |
| `手續費` | `fee` | Decimal，使用來源實際金額 |
| `交易稅` | `tax` | Decimal，使用來源實際金額 |
| `淨收付` | `net_cashflow` | Decimal，有正負號 |
| `利息` | `interest` | 若非零需對應受支援交易類型，否則例外 |
| 其餘費用/融資欄 | `other_charges`, `financing_*` | 原樣保存、V1 未支援時標記例外 |
| `下單來源別` | `order_channel` | 原始值保留供稽核 |

處理規則：剔除空列、兩種「總合」列；不可將來源表格的總合列當成股票交易；來源 65 筆交易為解析 fixture 的驗收基準。

### 4.3 CSV 與真正 Excel

允許欄位同義詞／指定映射表（如 `股數`、`成交股數`）；欄位不齊時拒絕並回報。CSV 首先 UTF-8-SIG/UTF-8，其他編碼需顯式允許（例如 CP950）；不得以錯誤字元替代後繼續匯入。

## 5. 標準資料模型

用 `@dataclass(frozen=True)` 寫入來源交易，數值統一用 `Decimal`（股數用 `int`）：

```python
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

Side = Literal["BUY", "SELL"]

@dataclass(frozen=True)
class Trade:
    source_id: str           # 來源檔 SHA256 + 列號 + 來源內序位
    file_name: str
    source_row: int
    account: str             # 使用者明確指定，不得跨帳戶匹配
    symbol: str              # 股票代號保留前導零
    name: str
    trade_date: date
    side: Side
    trade_type: str          # V1 已支援類型，例如 CASH
    currency: str
    unit_price: Decimal
    quantity: int
    gross_amount: Decimal
    fee: Decimal
    tax: Decimal
    interest: Decimal
    net_cashflow: Decimal
```

其他來源欄位放入 `source_extra` 或另一個原始快照資料結構，不得丟失不支援欄位的資訊。

`PositionLot`：`lot_id`, `buy_trade_id`, `original_quantity`, `remaining_quantity`, `date`, `symbol`, `account`, `currency`, `unit_price`, `original_buy_fee`、`original_row`。

`MatchSegment`：`buy_trade_id`, `sell_trade_id|None`, `matched_qty`, `remaining_flag`, `fragment_index`, `buy_fee_assigned`, `sell_fee_assigned`, `sell_tax_assigned`, `gross_buy_alloc`, `gross_sell_alloc`, `source_provenance`。

各類主鍵與關聯不可只靠 Excel 列號，因為分拆/插入會改變列號。

## 6. FIFO 核心演算法

### 6.1 前置處理

1. 讀取既有彙整表，依同帳戶、同代號、同幣別、同交易類型重建買進批次及歷史已售股數。
2. 載入本次新增交易，去除確定重複的來源列。
3. 依 `trade_date`、可用成交時間、核准的同日排序鍵排序。**禁止直接把來源檔的所有賣出放在所有買進前面或後面。**
4. 以 `(account, symbol, currency, trade_type)` 建立各自的 FIFO `deque`。
5. 對歷史資料不明確的開放庫存，先列例外；不可直接以表中買入股數減所有賣出股數後忽略拆分重複列。

### 6.2 參考偽程式

```python
for trade in chronologically_sorted_trades:
    key = (trade.account, trade.symbol, trade.currency, trade.trade_type)

    if trade.side == "BUY":
        fifo[key].append(new_lot(trade))
        continue

    pending = trade.quantity
    first_sell_segment = True

    while pending > 0:
        lot = earliest_open_lot_with_buy_date_not_after_sell(fifo[key], trade)
        if lot is None:
            record_unmatched_sell(trade, pending)
            break

        used = min(pending, lot.remaining_quantity)
        create_match_segment(
            lot=lot,
            sale=trade,
            quantity=used,
            assign_sell_fees=first_sell_segment,
        )
        lot.remaining_quantity -= used
        pending -= used
        first_sell_segment = False

        if lot.remaining_quantity == 0:
            close_and_pop(lot)

for lot in open_lots:
    create_open_segment(lot, lot.remaining_quantity)

# 每個買進 lot 的 fee 只附在其第一個輸出片段；
# 每筆賣出 trade 的 fee/tax 只附在第一個成功匹配的片段。
```

**實作關鍵**：若有賣出未匹配數量，應有 `blocking_issue`，不可把原始賣出手續費默默丟棄。若賣出只匹配部分，可把相關來源資訊保留在異常報告，正式財務輸出須先補齊歷史持倉或經使用者確認處理策略。

### 6.3 配對不變條件（invariants）

對每個買進批次：

```text
original_buy_qty == sum(matched_qty_of_buy_fragments) + open_remaining_qty
sum(buy_fee_of_all_fragments) == original_buy_fee
```

對每筆完整配對賣出：

```text
original_sell_qty == sum(matched_qty_of_sell_fragments)
sum(sell_fee_of_all_fragments) == original_sell_fee
sum(sell_tax_of_all_fragments) == original_sell_tax
```

對不完整配對的賣出：

```text
original_sell_qty == matched_qty + unmatched_qty
unmatched_qty > 0 => run_status != SUCCESS
```

全域：不得出現負股數、不同股票或不同帳戶交叉配對、賣出日期早於買進日期的配對、費用重複。

### 6.4 費用與金額尾差

- **原始費用採一次性歸屬，不做按比例攤提**。一買多段時買方費用只出現在第一段；一賣多段時賣方費用只出現在第一個成功匹配的片段。
- `gross_amount` 是券商原始成交金額總和的核對基準。拆分成交金額可以按股數比例以 `Decimal` 計算，將捨入尾差固定放在最後一段，使拆分後金額總和恰好等於來源 `gross_amount`。
- 買價、賣價顯示來源價格；新增拆列後的成本／收入／損益應依欄位與公式規則一致計算。不得因原有公式預設用固定費率而把來源實際費用改寫。
- 不提供虛構的成本基礎，不以稅務申報適用性作保證。

## 7. 既有 Excel 欄位映射（附件實測）

| 欄 | 原範本表頭 | 寫入策略 |
| --- | --- | --- |
| A | 買入日期 | 買進日期；Excel 日期型別、保留日期格式 |
| B | 賣出日期 | 有匹配賣出才填寫 |
| C | 股票代號 | 字串，不丟前導零 |
| D | 商品名稱 | 來源名稱 |
| E | 類別 | 現股（依已確認映射） |
| F | 買價 | 來源買進單價 |
| G | 股數 | 該拆分列買進所對應股數 |
| H | 手續費 | 原始買進手續費；只在該買進第一段寫一次 |
| I | 賣價 | 已匹配賣出的來源單價 |
| J | 股數 | 已匹配的賣出股數，未出售留空/0（依範本規範） |
| K | 手續費 | 賣出手續費，只在該賣出第一段寫一次 |
| L | 交易稅 | 賣出交易稅，只在該賣出第一段寫一次 |
| M | 利息 | 來源費用；不支援類型先擋下 |
| N | 融資金額 | V1 現股預設 0；非零檢查 |
| O | 融資年息 | 保留範本邏輯；現股避免不適當除零 |
| P | 成本 | 遵守範本公式與實際費用總和；不可硬寫固定值取代全部公式 |
| Q | 收入 | 遵守範本公式與實際費用總和 |
| R | 損益 | 遵守範本公式 |
| S | 獲利率 | 遵守範本公式，考慮空值與零分母 |
| T | 實際報酬率 | 遵守範本公式，考慮空值與零分母 |
| U | 券商 | 明確指定的帳戶／券商 |
| V | 大盤連動性 | 不推測、不覆寫既有手動資料 |
| W | 備註 | 可加入來源識別及異常說明；保留既有備註 |

**公式觀察**：範本含 `ROUNDDOWN(...)` 手續費、`IF(...)` 交易稅、損益與報酬率公式，並含 `_xlfn.DAYS(...)`；第 143 列可見 `SUM(H2:H142)` 等合計，第 144 列可見 `=P143-Q143`。對不同公式形態，須優先保留原式語意，不可用「重新填滿全部欄位」取代。

## 8. Excel Writer 與公式保護

### 8.1 必須採用的安全流程

1. `load_workbook(template, data_only=False, keep_links=True)` 載入公式，而非公式快取值。
2. 建立 **原檔 checksum + 工作副本**；僅在工作副本操作。
3. 先以領域模型產生**最終列順序／列內容／每列來源識別**，再寫入，不在 FIFO 處理時反覆插入工作表。
4. 找到真實資料區與合計列；不能假定第 143/144 列永久不變。支援以公式與欄位特徵定位。
5. 選擇最小範圍的列插入／替換；保留非目標欄位、字型、格式、合併儲存格、欄寬與列高。
6. 以已驗證的公式樣板複製相對參照（必要時使用公式 Translator），並**顯式修正**因新增／移動列而受影響的合計範圍、跨列引用與自訂名稱。
7. 對未知複雜公式、圖表、樞紐、外部連結、巨集等：先檢測並保護；若不能可靠保存，**中止而非悄悄破壞**。
8. 儲存至 `output/.tmp_<uuid>.xlsx`；關閉後重新開檔核對公式、列數、欄位與樣式；驗證成功才移動為帶時間戳記正式輸出。

### 8.2 Excel 公式管理限制

- `openpyxl` **不會執行 Excel 公式計算**；保存公式字串不等於已刷新 Excel 的計算結果。
- 插入列時，`openpyxl` **不會完整自動修正**所有其他儲存格／命名範圍／表格的引用；需自行維護及測試。
- 工作簿內有共享公式，需比較**展開後的有效公式**，不能只對底層 XML `<f>` 是否有文字做簡單比對。
- 規範：公式等價性、沒有 `#REF!`、彙總列包含全部有效交易列、既有非目標儲存格與樣式未被非預期修改。
- 可要求 Excel 下次開啟時重新計算，但**不得宣稱 openpyxl 已計算出最新公式值**。
- 若公式保真測試持續失敗，應先報告問題並縮小工作範圍，而不是改寫全表成數值。

### 8.3 安全性

- 不執行來源文件內的公式或巨集。
- 寫入來源文字時防止公式注入（對非數值文字以安全字串儲存，而非直接讓 `=` 被視為公式）。
- 無法解讀欄位、日期、股票代號時拒絕該筆並保留錯誤報告。

## 9. 去重、增量與來源追蹤

### 9.1 來源識別

- `file_sha256 = sha256(file_bytes)`；來源列 `source_row` 及同檔列序建立 `source_id`。
- 另算正規化交易指紋（帳戶、股票、日期、方向、數量、成交價、成交金額、費用、稅費等），供 **跨檔重疊警示**，但因缺乏券商成交編號，不可將指紋相同直接視為重複成交。
- 每次對帳產出本地 `.state/import_manifest.json` 或伴隨輸出的 audit manifest，記錄已匯入來源 ID 與結果檔關係。

### 9.2 再次執行

- **同批來源再次匯入**：以 manifest 確認已處理，預設跳過並回報。
- **不同檔案但交易疑似相同**：標記需人工確認，不自行刪除。
- **使用上次輸出檔做基底**：依其配套 manifest 進行增量；若 manifest 不存在，預設阻擋自動匯入，要求人工確認首批基準日與重疊情況。
- **補傳更早日期的買進或賣出**：可能改變歷史 FIFO 配對；應重新驗證整個受影響股票／帳戶的時間序列，不可只在尾部插入。

## 10. CLI 介面設計

範例（目標介面，**非已實作命令**）：

```powershell
uv run python -m backend.cli validate `
  --transactions "input/Statement (2).xls" `
  --summary "input/股票對帳單.xlsx" `
  --sheet "股票_2025" `
  --account "玉山" `
  --dry-run

uv run python -m backend.cli run `
  --transactions "input/Statement (2).xls" `
  --summary "input/股票對帳單.xlsx" `
  --sheet "股票_2025" `
  --account "玉山" `
  --output-dir "output"
```

設計中的參數：

| 參數 | 說明 |
| --- | --- |
| `--transactions` | 單檔或多檔（重複指定或使用 glob） |
| `--summary` | 既有彙整 Excel |
| `--sheet` | 明確指定工作表 |
| `--account` | 明確指定來源券商／帳戶 |
| `--output-dir` | 輸出目錄 |
| `--dry-run` | 只解析、比對與產生預覽／錯誤摘要，無正式 Excel 寫入 |
| `--strict` | 存在未配對或公式問題即阻擋成功輸出（預設啟用） |
| `--same-day-policy` | 同日順序策略，預設 `review`；其他選項須經使用者確認 |
| `--manifest` | 可指定相容的上一輪處理紀錄 |

出錯時使用非零 exit code、標準錯誤與 JSON 摘要；不可僅輸出 `success` 字樣卻未通過驗證。

## 11. 輸出命名、報告與檔案保護

```text
output/
├── 股票對帳單_2026-11-20_15-45-00.xlsx
├── 股票對帳單_2026-11-20_15-45-00_audit.json
└── 股票對帳單_2026-11-20_15-45-00_exceptions.csv
```

輸出時間以執行環境設定的本地時區為基準；應記錄 ISO-8601 時區偏移於 audit，避免不同時區機器同名衝突；若重名，再加安全序號或 UUID。

Audit 至少包含：`run_id`, `started_at`, `input_checksums`, `summary_checksum`, `output_checksum`, `sheet`, `account`, `parser_detected_type`, `trade_counts`, `matched_qty`, `unmatched_qty`, `split_count`, `fee_conservation`, `formula_audit`, `warnings`, `errors`, `source_to_segment_map`, `manifest_version`。

`.gitignore` 建議：

```gitignore
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
input/
output/
.state/
.env
.env.*
!*.example
```

## 12. 測試設計（pytest）

### 12.1 解析測試

- `Statement (2).xls` 需識別為 HTML，產出 **65 筆有效交易：BUY 22、SELL 43**；總合列剔除，日期 2025-10-03 至 2026-03-31。
- 真的 `.xls`、一般 `.xlsx`、UTF-8 CSV、UTF-8 BOM CSV、CP950 CSV（顯式允許）均可處理。
- 亂碼、缺欄、0/負股數、日期錯誤、非支援交易類型、格式偽造都應有可追蹤例外。

### 12.2 FIFO 主要測試案例

| ID | 情境 | 預期結果 |
| --- | --- | --- |
| F01 | 買進 1000、賣出 400 | 配對 400、未售 600 |
| F02 | 買進 A1000、B500、賣出 1300 | A1000+B300、未售 B200 |
| F03 | 買進 A1000、B500、先賣 400 再賣 900 | A400、A600、B300、未售 B200 |
| F04 | 買進已全部結清後再賣 | 不可重用已結清 Lot；標記未匹配 |
| F05 | 賣出日期早於唯一買進日期 | 不得配對、列異常 |
| F06 | 相同股票、不同帳戶 | 不可跨帳戶配對 |
| F07 | 不同股票、相同日期/數量 | 不可交叉配對 |
| F08 | 同日交易缺時分秒，必須依賴當日買進 | 預設列待確認 |
| F09 | 補入更早買進 | 受影響股票重新配對或阻擋增量，不得偷偷維持錯誤 FIFO |

### 12.3 金額、費用測試

- 每筆原始買進、賣出拆成多段，費用總和仍與原始來源完全一致。
- A1000 買進手續費 20，拆成 400+600，得到 20+0 而非 8+12 或 20+20。
- 一筆 900 股賣出配對 A600+B300，手續費 15、稅 27，得到第一段 15/27、第二段 0/0。
- 小數價與不同成交總額捨入，尾差配至最後一段；拆分後原始金額總和守恆。
- 同筆交易重跑不新增重複費用或股數。

### 12.4 Excel 保真測試

- 原始範本 SHA-256 在跑前跑後一致。
- 來源原有 23 欄、非目標工作表/儲存格與格式可保存。
- 已有資料的行內公式保留語意（含共享公式）；新增拆分列具有必要且可正確引用的新公式。
- 第 143 列 `SUM(...)`、第 144 列 `P143-Q143` 若移動，引用應更新且仍涵蓋全部新資料。
- 不得有非預期 `#REF!` 或公式被數值取代，需透過重新讀取輸出檔檢查。
- 如公式無法可靠更新，執行回報失敗，不輸出標記成功的報表。

### 12.5 負面／安全測試

- 空檔、錯副檔名、路徑不存在、檔案鎖定、CSV 公式注入、超大檔案、文字含 `<script>`、缺少 manifest 等。
- `--dry-run` 不會寫入原範本或正式輸出。
- 原始檔由原地只讀載入；不存在憑證上傳或外部 HTTP 呼叫。

## 13. Agent 開發順序與交付標準

| 階段 | 內容 | 完成條件 |
| --- | --- | --- |
| M0 | 讀 PRD/SPEC，確認已匯入 `.cursor` 規則及 Hooks 不會誤觸發 | 有工作清單、阻擋問題清單 |
| M1 | File Detector + Parser + 交易模型 | 通過附件 65 筆匯入測試 |
| M2 | 正規化、資料品質與現有持倉辨識 | 有完整可追溯交易清單 |
| M3 | FIFO、拆單、費用一次性歸屬 | F01–F09、費用守恆全過 |
| M4 | Excel writer、公式/格式保護與回讀 | 範本公式及彙總行測試通過 |
| M5 | 稽核、去重、CLI、輸出 | 同檔重跑零重複、原始檔不變 |
| M6 | 端到端測試、README、範例 | `uv run pytest` 全部通過、可再現結果 |

**不得提早宣稱完成**：若未配對賣出、公式引用不完整、費用總和不守恆，應標為 BLOCKED / NEEDS_REVIEW，而不是 SUCCESS。

## 14. 需要先與使用者確認的政策

1. 同日交易沒有時間時，是否允許按照來源列順序配對？（預設：待確認）
2. 來源帳戶/券商如何指定？（預設：CLI 必填 `--account`）
3. 首次匯入時，如何處理既有彙整表與交易檔日期重疊？（預設：要求人工確認）
4. 2026 年成交要寫入 `股票_2025` 還是新 Sheet？（預設：`--sheet` 明確指定）
5. 賣出拆分時，費用是否如買進一樣留在第一段？（本 SPEC 暫定如此，待確認）
6. 非現股、現股當沖或其他有融資／利息欄位的資料，是否另訂規則？（預設：暫停該交易）

## 15. 專案開發注意事項

- 不要直接將 `Learn2Card` 舊專案的 PRD、SPEC 當成本系統需求；`trading_report` 以本文件和 `PRD.md` 為準。
- 已匯入的 `backend-rule.mdc` 設有 `alwaysApply: true`，包含 `backend/`、Python、`uv`、`pyproject.toml` 等要求，需先確認與本規格一致。
- 先檢查 `.cursor/hooks.json` 是否仍引用不存在的 `hooks/send_line_notification.py`；不需要 LINE 通知就移除該事件，避免 Agent 停止時報錯。
- 未經使用者同意不得刪除原始檔、改動既有 Excel 母檔、發送檔案到外部服務、建立任何付費 API 依賴。

