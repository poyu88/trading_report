# SPEC.md — 股票交易正規化／SQLite／FIFO／明細報表技術規格

> 專案：`trading_report`
> 文件版本：v2.0（全新 Database-first 設計）
> 日期：2026-11-20
> 依據：同版 `PRD.md` 與來源檔 `Statement (2).xls`、欄位參考 `股票對帳單.xlsx`
> 狀態：可供 Cursor Agent 實作的設計基線；尚未實作及驗證。

## 1. 架構與邊界

```text
[input: .csv / .xls / .xlsx]
          │
          ▼
   FileDetector + Parsers   ← 券商 profiles/*.yaml（或 .json）
          │
          ▼
   RawRow → Normalizer → Validator
             │       └───────> import_errors
             ▼
        SQLite (本機)
   ┌─────────┼───────────────────────────────┐
   │         │                               │
 raw_rows   trades + accounts       import_batches
             │
             ▼
      FIFO Matcher (純業務邏輯)
             │
             ▼
      allocation_runs + allocations + exceptions
             │
             ▼
     Report Projector → Detail XLSX Writer ──> detail.xlsx
                        │                     (僅表頭 + 明細列)
                        └──────────────────> audit.json / exceptions.csv

     [P1] Stats Projector ───────────────────> stats.xlsx（另一個檔案）
```

**關鍵不變條件**：`trades` 永遠表示未拆的券商交易，`allocations` 記錄拆出的 FIFO 關係；Excel 為可重建的投影。不得以 Excel 做交易狀態管理，也不在 Detail XLSX 內產生統計／加總資料列。

## 2. 免費技術棧

| 元件 | 技術 | 角色 | 是否必需 |
|---|---|---|---|
| Runtime | Python 3.11+ | 跨平台核心程式 | P0 |
| 套件與鎖定 | `uv`、`pyproject.toml`、`uv.lock` | 管理虛擬環境、可重現安裝 | P0 |
| DB | **SQLite 3**（本機檔案） | 原始、正規化、配對、稽核資料 | P0 |
| ORM | `SQLAlchemy` 2.x | ORM／交易／SQLite 封裝 | P0 |
| Migration | `Alembic` | Schema 版本升級 | P0 |
| CSV | Python `csv` | CSV 解析 | P0 |
| 真 Excel | `python-calamine` | 讀 `.xls` 與 `.xlsx` | P0 |
| HTML 偽 XLS | `beautifulsoup4` | 讀 HTML table | P0 |
| Excel 輸出 | `openpyxl` | 生成全新的 `.xlsx`，不依賴 Excel 軟體 | P0 |
| Decimal & FIFO | `decimal` / `collections.deque` | 精確金額／FIFO 序列 | P0 |
| 日期／雜湊／CLI | `datetime` / `hashlib` / `argparse` / `json` | 標準函式庫 | P0 |
| 測試／檢查 | `pytest` / `ruff` | 單元、整合、靜態檢查 | 開發 P0 |
| 介面 | `streamlit` | 本機瀏覽器操作介面 | P1 |

- 核心依賴優先免費開源；不用收費 API、Office COM、自架伺服器或第三方資料庫服務。
- SQLite 是單機資料庫檔，SQLite 同時間只能有一個寫入交易；CLI 本機單使用者工作量足夠。未來多人協作才考慮 PostgreSQL。
- SQLite `NUMERIC` 可能觸發浮點轉換；**價格／金額儲存為規範化十進位字串 `TEXT`**，在 Python 使用 `Decimal` 進行運算；不使用 SQLite `SUM()` 聚合這些 TEXT 金額，也不使用 SQLite REAL 儲存資金。
- `quantity` 使用整數 `INTEGER`（本版台股股數），含比例等非整數數值在 Python `Decimal` 計算；可在日後增加金額整數最小單位策略。
- 來源 profile 第一版採 `JSON`（標準函式庫）而非額外引入 YAML 依賴；檔案放在 `configs/profiles/*.json`。

### 2.1 Windows / Cursor Terminal 初始化

```powershell
# 專案根目錄：若沒有 pyproject.toml 才需執行
uv init --python 3.11
uv add sqlalchemy alembic python-calamine beautifulsoup4 openpyxl
uv add --dev pytest ruff

# 資料庫 schema migration 由 Agent 建立 Alembic migrations 後再執行
uv run alembic upgrade head
uv run pytest
uv run ruff check .
```

> `uv init` 需視既有專案結構調整；不要在已有專案設定時盲目覆寫 `pyproject.toml`。Dependencies 的版本由 `uv.lock` 鎖定，不依賴 `latest` 浮動版本。

## 3. 專案目錄

```text
trading_report/
├── .cursor/                    # 使用者已建立的 Cursor Rules／Hooks，可另審查
├── hooks/
├── docs/
│   ├── PRD.md
│   └── SPEC.md
├── configs/
│   └── profiles/
│       ├── statement_html_v1.json
│       └── esun_xlsx_v1.json
├── backend/
│   ├── __init__.py
│   ├── cli.py                   # python -m backend.cli
│   ├── config.py
│   ├── domain/
│   │   ├── models.py            # Decimal, Trade, Lot, Allocation
│   │   └── exceptions.py
│   ├── ingest/
│   │   ├── detector.py
│   │   ├── csv_parser.py
│   │   ├── excel_parser.py
│   │   ├── esun_xlsx_parser.py  # 玉山 XLSX 結構重塑
│   │   ├── html_parser.py
│   │   ├── mapping.py
│   │   ├── normalizer.py
│   │   └── validator.py
│   ├── db/
│   │   ├── models.py            # SQLAlchemy ORM
│   │   ├── session.py
│   │   └── repositories.py
│   ├── services/
│   │   ├── import_service.py
│   │   ├── fifo_matcher.py
│   │   ├── allocation_service.py
│   │   ├── reconciliation.py
│   │   └── backup_service.py
│   └── reports/
│       ├── detail_projector.py
│       ├── detail_writer.py
│       ├── field_schema.py
│       └── audit_writer.py
├── alembic/
│   └── versions/
├── tests/
│   ├── fixtures/               # 合成資料；不得提交真實對帳單
│   ├── test_detector.py
│   ├── test_normalizer.py
│   ├── test_import_idempotency.py
│   ├── test_fifo.py
│   ├── test_fee_once.py
│   ├── test_opening_lots.py
│   ├── test_report_schema.py
│   ├── test_report_no_totals.py
│   └── test_end_to_end.py
├── data/                        # 私有，不納入 Git
│   ├── trading.db
│   ├── source_archive/
│   └── backups/
├── input/                       # 私有，不納入 Git
├── output/                      # 私有，不納入 Git
├── pyproject.toml
├── uv.lock
├── .gitignore
└── README.md
```

## 4. 來源辨識與解析

### 4.1 檔案型態偵測優先序

| 實際型態 | 偵測條件 | 解析器 |
|---|---|---|
| 真二進位 XLS | OLE magic `D0 CF 11 E0 A1 B1 1A E1` | `python-calamine` |
| XLSX | ZIP signature + 必要 Excel 內部路徑 | `python-calamine` |
| HTML 偽 XLS | 解碼後存在可解析的 `<table>` | `BeautifulSoup` |
| CSV | 可用候選編碼解碼、分隔符及欄位驗證通過 | `csv` |
| 未知/破損 | 以上均無法確認 | 拒絕，記錄原因 |

- 檔案副檔名僅作參考；拒絕可疑超大檔案或檔案中執行內容，不載入外部連結／巨集。
- CSV 解碼優先 `utf-8-sig`、`utf-8`，再以設定／人工選擇 `cp950` 或 `big5`；有多個看似可解碼的結果時以欄名驗證，不能用 `errors="ignore"`。
- 保留來源列號：HTML 的 table row index、CSV 實際 record number、Excel sheet+row；來源工作表由 profile 指定或要求選擇。
- `python-calamine` 讀取日期可能得到日期物件、序號或字串；正規化器要依欄位型別與 workbook 日期系統處理，不能把不明數值自行當日期。

### 4.2 本次來源實例及 Mapping Profile

來源 `Statement (2).xls`：實際 HTML 表格 18 欄，65 筆現股交易。示範 profile：

```json
{
  "profile_id": "statement_html_v1",
  "version": 1,
  "source_format": "html_table",
  "table_index": 0,
  "required_headers": ["商品", "成交日", "買賣別", "成交股數"],
  "column_map": {
    "商品": "symbol_and_name",
    "成交日": "trade_date",
    "買賣別": "side_raw",
    "幣別": "currency_raw",
    "成交價": "unit_price",
    "成交股數": "quantity",
    "成交金額": "gross_amount",
    "手續費": "commission",
    "交易稅": "tax",
    "淨收付": "net_settlement",
    "利息": "interest",
    "融資金額/ 擔保價款": "margin_amount",
    "下單來源別": "order_channel"
  },
  "exclude_row_prefixes": ["總合("]
}
```

*備註：HTML 表頭的空白與 `<br>` 必須先正規化成統一字串；profile 的 key 用解析後的標準化表頭比對，且要明確回報未匹配欄。正式 profile 需涵蓋其餘 18 欄原始欄位的留存。*

### 4.2.1 玉山真 XLSX（`esun_xlsx_v1`）

來源 `玉山.xlsx`：真 XLSX，資料區表頭非第 1 列。結構規則：

| 列類型 | 特徵 | 處理 |
|---|---|---|
| 日期列 | 僅成交日（date／可解析日期字串），其餘業務欄空白 | 更新「目前日期」；本身不產生交易 |
| 來源交易候選列（已支援） | 交易類別為四種之一，含名稱／股數／單價／價金／費用 | 繼承目前日期；下一列應為代號列；計入 `recognized_*`／來源核對；正規化成功後可入 `trades` |
| 來源交易候選列（未支援） | 交易類別非四種之一（如融資／融券／配股）且非結構列 | 仍輸出扁平列供 `normalize`；列 `UNSUPPORTED_TRADE_TYPE`，**不得靜默丟棄**；寫入 `raw_rows` error；**不入** `trades`；**不計入**來源核對 |
| 代號列 | 交易類別空白，股票名稱欄為數值代號（可能為負） | 與上一成交候選列合併；代號正規化為正整數字串 |
| 小計列 | 儲存格含「小計」 | 排除，不入庫、不進候選列 |
| 頁尾／說明 | 「資料筆數」「說明」等 | 排除；頁尾「資料筆數／價金／費／稅」供來源核對基準 |

**語意對照**：來源交易候選列 ⊇ 已正規化交易 ∪ 未支援交易；來源核對只比較「已支援四類型合計」與頁尾，故頁尾若含未支援列則 `matched=false` 為預期訊號，不是把未支援列改計入核對。

示範 profile（欄名以正規化後比對）：

```json
{
  "profile_id": "esun_xlsx_v1",
  "version": 1,
  "source_format": "esun_xlsx",
  "required_headers": ["交易類別", "股票名稱", "成交股數", "成交單價", "成交價金"],
  "column_map": {
    "交易類別": "side_raw",
    "股票名稱": "name",
    "成交股數": "quantity",
    "成交單價": "unit_price",
    "成交價金": "gross_amount",
    "手續費": "commission",
    "交易稅": "tax",
    "利息": "interest",
    "淨收付金額": "net_settlement",
    "成交日": "trade_date",
    "股票代號": "symbol"
  },
  "exclude_row_prefixes": ["資料筆數", "說明"],
  "side_map": {
    "現股買進": "BUY",
    "現股賣出": "SELL",
    "現沖買進": "BUY",
    "現沖賣出": "SELL"
  },
  "trade_type_map": {
    "現股買進": "CASH",
    "現股賣出": "CASH",
    "現沖買進": "DAY_TRADE",
    "現沖賣出": "DAY_TRADE"
  },
  "unsupported_sides": {},
  "default_currency": "TWD",
  "date_formats": ["%Y/%m/%d", "%Y-%m-%d"],
  "gross_tolerance": "1"
}
```

**現沖與一般現股 FIFO 邊界**：`現股*` → BUY／SELL、`trade_type=CASH`；`現沖*` → BUY／SELL、`trade_type=DAY_TRADE`；皆可入庫。DAY_TRADE 與 CASH 為獨立 lot pool。同日無序現沖**必須**與當日對應買賣相互 FIFO（當日 BUY 建 lot → 當日 SELL FIFO，含先賣後買），**不得**因缺 time／sequence 標 `ORDER_AMBIGUITY` 而跳過；lot 不跨日、不消耗 CASH。未配平進 `reconciliation_issues`，不是解析錯誤。缺日期繼承或缺次列代號 → 列級驗證錯誤。profile／結構失敗 → apply 整批不寫入並 rollback。

### 4.3 Canonical Trade 模型

```python
@dataclass(frozen=True)
class Trade:
    trade_id: str
    account_id: str
    source_row_id: str
    symbol: str                 # 股票代號，文字，不得 int 化
    name: str | None
    trade_date: date
    trade_time: time | None
    trade_sequence: int | None # 真實或人工核准的順序；不可自行虛構
    side: Literal["BUY", "SELL"]
    trade_type: Literal["CASH", "DAY_TRADE"]
    currency: str               # 預設 TWD，僅來源/設定有證據時
    quantity: int
    unit_price: Decimal
    gross_amount: Decimal
    commission: Decimal
    tax: Decimal
    interest: Decimal
    net_settlement: Decimal | None
```

`trade_id` 可使用 UUID；來源紀錄 ID 及可疑重複 fingerprint 應分開，不以 fingerprint 直接當交易唯一鍵。

### 4.4 正規化規則

- `symbol_and_name` 拆為股票代碼及名稱；股票代碼始終為字串。
- `現股買進/賣出`、`現沖買進/賣出` 經 `side_map` → BUY／SELL；`trade_type_map` → CASH／DAY_TRADE；其他語意一律先列未支援例外（`unsupported_sides`／`UNSUPPORTED_TRADE_TYPE`）。
- 玉山次列代號：來源數值取絕對值後轉整數字串（如 `-4971.0` → `4971`）；禁止以 float 科學記號或帶小數點字串入庫。
- 現沖股數、單價、成交金額、手續費、交易稅採與現股相同正規化；費用用來源值，不重算不分攤。
- `臺幣`／`TWD` 標準化為 `TWD`；未知幣別不得推定。無幣別欄時僅在 profile 明示 `default_currency` 時使用。
- 小數、逗號、負號採明確 parser；`Decimal(text.replace(',', ''))`；不得用 `float()` 做金額計算。
- 日期從 `YYYY/MM/DD` 等已確認格式轉為 `date`，禁止不明格式的月份／日期猜測；玉山成交列繼承日期列。
- `quantity` 必須是正整數；單價、成交金額、費用不得為負（若出現應透過交易類別規則核實）；淨收付可為負（買進流出）。
- 交易原始 JSON 完整保留，包括其他稅費／利息／融資欄位，即使 V1 不做對應交易類型處理。
- 對來源帳戶及證券別沒有充分資訊時，由使用者指定並寫入批次，不能偷偷使用另一券商帳戶。

## 5. SQLite Schema（供 Alembic 建表）

**ORM 以此表格為準；所有主鍵、外鍵、唯一鍵、檢查限制由 migrations 管理。**

| 表名 | 主鍵 / 核心欄位 | 唯一與關聯／責任 |
|---|---|---|
| `brokers` | `id`, `name` | 券商主檔 |
| `accounts` | `id`, `broker_id`, `account_label` | 券商＋帳戶唯一；防止跨帳戶 FIFO |
| `import_batches` | `id`, `account_id`, `file_sha256`, `filename`, `profile_id`, `profile_version`, `imported_at_utc`, `status` | 同帳戶來源重複管制；保留 reprocess 版本與狀態 |
| `raw_rows` | `id`, `batch_id`, `sheet_name`, `row_index`, `raw_json`, `row_sha256`, `parse_status`, `error_code` | 原始列與解析結果；`UNIQUE(batch_id, sheet_name, row_index)` |
| `trades` | `id`, `raw_row_id`, `account_id`, `symbol`, `trade_date`, `trade_time`, `sequence`, `side`, `trade_type`, `currency`, `quantity`, `unit_price_txt`, `gross_amount_txt`, `commission_txt`, `tax_txt`, `interest_txt`, `net_settlement_txt`, `external_trade_id` | `UNIQUE(raw_row_id)`；經驗證正規化交易，原值不因 FIFO 改變 |
| `opening_lots` | `id`, `account_id`, `symbol`, `currency`, `buy_date`, `quantity`, `unit_cost_txt`, `approval_note`, `source_reference`, `status` | 使用者核准的期初持倉；不能憑空建立成本 |
| `allocation_runs` | `id`, `algorithm_version`, `input_fingerprint`, `started_at_utc`, `finished_at_utc`, `status`, `config_json` | 每次配對版本；不可覆蓋舊版本 |
| `fifo_allocations` | `id`, `run_id`, `buy_trade_id`, `opening_lot_id`, `sell_trade_id`, `allocated_quantity`, `sequence_no` | 買進來源二選一；一筆賣出可對多筆買進；`allocated_quantity > 0` |
| `reconciliation_issues` | `id`, `run_id`, `batch_id`, `trade_id`, `issue_code`, `severity`, `detail_json`, `resolved_at_utc` | 待處理例外；指向資料來源 |
| `report_runs` | `id`, `allocation_run_id`, `report_type`, `file_path`, `file_sha256`, `created_at_utc`, `status`, `schema_version` | 報表版本、輸出追溯 |

### 5.1 核心 SQL 約束示意

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY,
    raw_row_id TEXT NOT NULL UNIQUE REFERENCES raw_rows(id),
    account_id TEXT NOT NULL REFERENCES accounts(id),
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,       -- ISO YYYY-MM-DD
    trade_time TEXT,                -- 可空；原始有值才填
    trade_sequence INTEGER,         -- 無可信順序時 NULL
    side TEXT NOT NULL CHECK (side IN ('BUY','SELL')),
    trade_type TEXT NOT NULL CHECK (trade_type IN ('CASH', 'DAY_TRADE')),
    currency TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_txt TEXT NOT NULL,
    gross_amount_txt TEXT NOT NULL,
    commission_txt TEXT NOT NULL,
    tax_txt TEXT NOT NULL,
    interest_txt TEXT NOT NULL DEFAULT '0',
    net_settlement_txt TEXT,
    external_trade_id TEXT
);
CREATE INDEX IF NOT EXISTS ix_trades_fifo
ON trades(account_id, symbol, currency, trade_date, trade_time);
```

> 上面是部分示例 DDL，不是完整 migration；不應與 Alembic 自動產生的正式 schema 重複執行。正式 migration 仍應額外驗證 decimal 字串格式、FK、唯一約束、單側 opening lot 欄位以及批次狀態轉移。

### 5.2 Decimal 精度契約

- SQLite 持久化：`Decimal` 轉成規範化十進位字串（例如 `"172.00"`）；讀取時轉回 `Decimal`。
- 欄位驗證：價格 `> 0`，成交價金 `>= 0`，費用 `>= 0`；各幣別允許的小數位與四捨五入政策由設定控制。
- 運算：絕不使用 Python `float`、SQLite `REAL` 或 SQL `SUM(CAST(text AS REAL))` 計算財務結果。
- 預設台幣金額輸出至小數 2 位（保留來源實際精度作為 DB 原值），實際券商整元舍入可透過 profile 定義；不可推定所有券商相同。

### 5.3 批次與交易去重

- 同帳戶、同檔案內容雜湊、同一來源處理版本：重複匯入返回已有批次，不新增交易。
- 同一檔內 `raw_rows` 有唯一座標；可能相同的兩筆實際成交（同日同價同量）仍可分開留存。
- 跨檔可能重疊：若提供可靠 `external_trade_id`，使用券商＋帳戶＋外部 ID 確認；否則建立 `POTENTIAL_DUPLICATE` 例外供人工確認，暫不自動抹除。
- Profile 更新後重新解析來源，需明確 `reprocess` 流程與版本、審計事件；避免同一交易重複產生多筆 active 記錄。
- 檔案封存可使用 `data/source_archive/<sha256>.<ext>`，目錄與交易 DB 都不能納入 Git。

## 6. FIFO 演算法規格

### 6.1 Scope 與排序

分組鍵：`account_id, symbol, currency, trade_type`；CASH 與 DAY_TRADE 為獨立 pool。

- **CASH**：組內依可證實成交順序處理。日內時間或原始序號缺失、且影響買賣合法先後或 FIFO lot 選擇時，產生 `ORDER_AMBIGUITY`；不能僅憑輸入檔排序捏造交易先後。明確較早日期的 BUY 可配對較晚日期的 SELL；不得配對未來買進。
- **DAY_TRADE**：僅同日配對。同日無序現沖**不得**標 `ORDER_AMBIGUITY` 而跳過；對每個交易日先將當日全部 DAY_TRADE BUY 建成 lot，再以 FIFO 將當日 DAY_TRADE SELL 配入（含檔內先賣後買）。lot **不跨日**、**不消耗 CASH**。未配平剩餘進 `reconciliation_issues`。
- 買賣同股票但不同帳戶不得直接相互抵銷。
- `opening_lots` 必須由核准的真實成本與數量建立，並僅參與 **CASH** FIFO。

### 6.2 Python 型別與偽程式碼

```python
@dataclass(frozen=True)
class Allocation:
    run_id: str
    buy_trade_id: str | None
    opening_lot_id: str | None
    sell_trade_id: str
    quantity: int
    order: int

@dataclass
class LotRemaining:
    buy_trade_id: str | None
    opening_lot_id: str | None
    available: int
    trade_date: date

# 前置：輸入已按「已確認的」順序排序；否則先報 ORDER_AMBIGUITY
fifo = deque()
for trade in verified_trades:
    if trade.side == 'BUY':
        fifo.append(LotRemaining(trade.id, None, trade.quantity, trade.trade_date))
        continue

    sell_left = trade.quantity
    while sell_left > 0 and fifo:
        lot = fifo[0]
        matched = min(lot.available, sell_left)
        save_allocation(buy=lot, sell=trade, quantity=matched)
        lot.available -= matched
        sell_left -= matched
        if lot.available == 0:
            fifo.popleft()

    if sell_left > 0:
        record_issue('INSUFFICIENT_PRIOR_BUYS', trade.id, sell_left)

# fifo 尚存股數即未售；未配對賣出不可硬配到未來買進。
```

> 此為核心示意，正式實作須把 `opening_lots` 初始佇列、同日排序判定、交易驗證、run 原子性與取消重算納入。FIFO matcher 不應直接讀取或寫入 Excel／SQLite；由 service 負責輸入／存回。

### 6.3 配對不變條件

對每個買進 `b`：`sum(allocation.qty where buy=b) <= buy.quantity`。

對每個賣出 `s`：`sum(allocation.qty where sell=s) <= sell.quantity`。

每筆 allocation：`qty > 0`，同帳戶、同股票、同幣別；買進不晚於賣出（若同日依可信排序）。

核對指標：`buy_qty = sold_allocated_qty + unsold_qty`；`sell_qty = allocated_sell_qty + unmatched_sell_qty`。

重新執行相同演算法版與同一批有效交易，得到同樣順序／數量／配對 ID 映射（忽略 run UUID）。

### 6.4 期初庫存與未匹配

- V1 **不把 `股票對帳單.xlsx` 當成交易事實**。附件只是欄位模板。
- 如果需要已存在的股票庫存，使用者另行提供有成本、日期、帳戶、股票與數量的經核准期初 lot（CSV 或手動資料）。沒有成本不得產生假損益。
- `INSUFFICIENT_PRIOR_BUYS` 阻擋正式完成狀態。`report detail --allow-partial` 產 `DRAFT` 並附例外；主明細僅包含可信已配對／未售買進，未配對賣出獨立報告。

## 7. 費用不拆分規則與報表分段投影

### 7.1 不修改原始交易

- `trades.commission_txt`、`trades.tax_txt` 永遠記來源實際數字。
- `fifo_allocations` 僅記配對數量、買／賣連結，不攜帶被拆算的費用。
- 明細列由 `detail_projector` 在匯出時組裝，不能把拆段結果反寫為假交易。

### 7.2 第一片段費用落點

對**同一買進來源**所有報表片段按排序鍵（有明確出售日期先排配對片段、其餘未售尾數最後；同日再依已確認成交順序與 allocation sequence）排序：第 1 列帶入完整買進手續費／相關一次性費用；其餘列 `0`。

對**同一賣出來源**的所有配對片段按 FIFO allocation sequence 排序：第 1 列帶入完整賣出手續費、交易稅與利息（若適用）；其餘列 `0`。未配對賣出殘量不另複製一筆費用；費用落點仍以「第一個已配對片段」為準（若該賣出完全無配對，費用僅留在資料庫／例外／配套未配對明細的費用說明，不假稱主明細 A～W 已納入）。

如果一筆交易因阻擋性例外完全不能映射進主明細，費用應保留在資料庫與例外核對紀錄，不能假稱主報表費用已守恆。稽核需同時區分「來源全部費用」和「已納入主報表交易的費用」。

### 7.3 價金與成本計算

1. 買賣股數只按 `allocation.quantity` 拆（主明細已配對列）；單價、日期、代號及來源 ID 不變。原始 `trades` 的 `gross_amount`／`unit_price`／`quantity` **不得**因拆片段而被改寫。
2. 片段成交價金在 Python 用 `Decimal` 計算（**禁用 float**）。對每一筆來源交易（買／賣各自、依 `trade_id` 分組），將該交易的所有片段股數（買：已配對＋未售殘量；賣：**已配對＋未配對殘量**，殘量必須納入 `pieces`）依 **FIFO 配對／殘量順序**排列後，以下列演算法分配價金（**廢止**「按原始價金比例拆＋尾差預先歸最後片段／餘額法」）：
   - 對每個片段 `i`：`truncated_i = TRUNC(fragment_qty_i × original_unit_price)`（朝零截斷為整數 `Decimal`；**含最後片段**，不得對最後片段改用餘額法略過截斷）。
   - `calculated_total = Σ truncated_i`；`difference = original_gross_amount − calculated_total`。
   - 若 `difference == 0`：不調整。
   - 若 `|difference| ≤ 1`（容許差 `Decimal("1")`）：最後片段 `+= difference`，並於 audit／守恆表記錄調整額與原因；補差後必須 `Σ最終價金 == original_gross_amount`。
   - 若 `|difference| > 1`：**不**自動補差；保留截斷結果；發出 `AMOUNT_CONSERVATION_OUT_OF_TOLERANCE`（必填：`trade_id`、原始價金、截斷合計、`difference`、各片段 qty／truncated／最終價金）；該筆價金守恆失敗，`conservation_ok` 不得因該筆變為 true。
   - **第一／最後片段**定義依 FIFO 配對／殘量順序，**不得**被 Excel 顯示排序改寫。
   - **禁止** `gross × qty / total_qty` 比例分配；**禁止**最後片段用 `total − allocated` 取代先做 `TRUNC(qty×price)`。
   - **不得把原始手續費／稅費／利息依比例分攤**。
3. 公式（P／Q／R 以截斷並經容許內補差後的片段價金為基礎；整數 `Decimal` 路徑，禁用 float）：
   - `cost`／成本 = `buy_gross + buy_commission`（買費僅第一買進片段）
   - `income`／收入 = `sell_gross - sell_commission - sell_tax - sell_interest`（賣費／稅／息僅第一賣出費用片段）
   - `profit`／損益 = `income - cost`（僅已配對且有成本來源）
4. 利息三態：來源有值 → 採用；確認不適用 → `0`；應有卻缺漏 → 驗證異常（不得默默當 0）。明確字串 `"0"` 視為已知 0。
5. 注意：若某一買進的一次性買費放在尚未賣出的片段（特殊排序情況），單筆已實現損益與經濟學攤提成本不同；本版遵照**使用者指定不分攤費用**的報表呈現規則，另以 audit 說明。不得偷偷換成加權分攤。
6. 未賣出的片段：賣價、賣量、賣費、賣稅、利息、收入、已實現損益、獲利率皆為 `None`／Excel 空白；成本可保留買入片段價金與首次買費。
7. 未配對賣出殘量：**不**插入虛構買進承載於主明細 A～W；**不**計算完整已實現損益（成本／損益不得以 `0` 冒充）。殘量股數、價金與費用落點說明見配套明細與 exceptions／audit。
8. `實際報酬率`、`大盤連動性` 未知定義時保持空白；不得自行複製另一欄位結果。
9. A～W 欄名義／順序／型別不變（見 §8.1）；F／I 保留來源單價小數；G／J 為本列片段股數；P／Q／R 為依本節計算之金額。

## 8. Excel 明細輸出契約（最重要）

### 8.1 23 欄 schema 與型別

| 欄位 | 名稱 | 型別 | 值的來源 |
|---|---|---|---|
| A | 買入日期 | Excel 日期 | BUY trade 日期／Opening lot 日期 |
| B | 賣出日期 | Excel 日期或空 | SELL trade 日期 |
| C | 股票代號 | 字串（`@`） | `symbol`，保留前導零 |
| D | 商品名稱 | 字串或空 | `name` |
| E | 類別 | 字串 | `現股` |
| F | 買價 | 數值 | BUY unit price |
| G | 股數（買） | 正整數 | allocation quantity／open remaining |
| H | 手續費（買） | 數值 | 該來源買進費用僅第一列填入 |
| I | 賣價 | 數值或空 | SELL unit price |
| J | 股數（賣） | 正整數或空 | allocation quantity |
| K | 手續費（賣） | 數值或空 | 該來源賣費僅第一列填入 |
| L | 交易稅 | 數值或空 | 該來源賣稅僅第一列填入 |
| M | 利息 | 數值或空 | 賣出利息（若適用）落於第一賣出費用片段；見 §7.2–7.3 |
| N | 融資金額 | 數值或空 | V1 現股無則空白 |
| O | 融資年息 | 數值或空 | V1 現股無則空白 |
| P | 成本 | 數值 | 本列買入片段價金（§7.3 截斷±容許補差後）＋一次性買費 |
| Q | 收入 | 數值或空 | 本列賣出片段價金（§7.3 截斷±容許補差後）－一次性賣費／稅／利息 |
| R | 損益 | 數值或空 | Q − P（已售）；未配對不得以 0 冒充 |
| S | 獲利率 | 數值或空 | R / P（P > 0） |
| T | 實際報酬率 | 數值或空 | 未定義前空白 |
| U | 券商 | 字串 | broker.name |
| V | 大盤連動性 | 數值或空 | 未定義前空白 |
| W | 備註 | 字串或空 | 可顯示原始備註；部分配對賣出之第一片段須註記費用全額落點與殘量（非合計） |

- 標題列只放**一次**在 `A1:W1`；每個 `A2:Wn` 都是同一個 `DetailRow` schema。
- **禁止** `SUM(...)` 合計列、`總合` 文字列、跨欄標題列、空白分隔列、結尾說明列或嵌入 KPI。
- 無資料時只有表頭，不輸出 `查無資料` 作為資料列。
- 為保持相容，A～W 欄名的文字可沿用附件的原始顯示（有些帶空格），但程式內部使用固定 canonical key。
- **不要以舊工作表作為要寫入的目標範本**；由程式新建工作簿、設定相似版式與欄序，避免繼承既有第 143、144 列統計公式及表格資料。
- 交易 ID、配對 ID、FIFO 批次 ID 存在 `..._audit.json`／`..._detail_index.csv`（如有必要），不塞入 A～W 混淆原有欄位。

### 8.2 資料列產生方法

```python
@dataclass(frozen=True)
class DetailRow:
    buy_date: date
    sell_date: date | None
    symbol: str
    name: str | None
    trade_type_label: str
    buy_price: Decimal
    buy_qty: int
    buy_commission: Decimal
    sell_price: Decimal | None
    sell_qty: int | None
    sell_commission: Decimal | None
    sell_tax: Decimal | None
    interest: Decimal | None
    margin_amount: Decimal | None
    margin_annual_rate: Decimal | None
    cost: Decimal
    income: Decimal | None
    profit: Decimal | None
    profit_rate: Decimal | None
    actual_return_rate: Decimal | None
    broker: str
    market_correlation: Decimal | None
    note: str | None
```

- 每筆已配對 allocation 形成一列；每筆買進尚有餘額形成一列；完全未配對的賣出不形成偽造的已售列（不插入虛構買進）。
- 部分配對賣出：主明細已配對列之賣出價金僅反映片段股數；第一片段 W 備註應含「費用全額落點；尚有未配對殘量；本列損益非完整原始交易損益」。
- 決定性排序建議 `account, symbol, buy_date, buy_provenance_order, sell_date nulls_last, allocation.sequence_no`，可預覽／設定但不得改變 FIFO 結果。
- 輸出前先在記憶體驗證 `DetailRow` schema；失敗不能繼續寫 XLSX。

### 8.2.1 配套報表：FIFO 配對及未配對明細

另產時間戳檔（建議檔名含「FIFO配對及未配對明細」），與主明細 A～W **欄義分離**：

| 要求 | 說明 |
|---|---|
| 列語意 | 每一片段一列，明確標示 `MATCHED`／`UNSOLD_BUY`／`UNMATCHED_SELL` |
| 未配對列 | 保留股數、成交價金、手續費／稅／利息（依費用一次規則與落點說明）、來源 `sell_trade_id` |
| 禁止 | 未配對列不得填成本／已實現損益為 `0` 冒充已實現；不得把整筆原始價金重複記入已配對與未配對 |
| 守恆 | 對每筆來源賣出：已配對片段價金合計＋未配對殘量價金＝原始 `gross_amount` |

### 8.2.2 例外與 audit 金額守恆欄

`exceptions.csv`／`audit.json` 對 `INSUFFICIENT_PRIOR_BUYS`（及其他賣出殘量）應可追溯：`unmatched_quantity`、`unmatched_gross`、`matched_quantity`、`matched_gross`，以及費用落點說明（例如費用是否已落在主明細第一片段）。

### 8.3 格式與型別維護

- `openpyxl.Workbook()` 建立新的 Excel，不讀舊統計工作表作為輸出底稿。
- 文字欄：`C, D, E, U, W` 設文字型別／顯示格式，避免股票代號被當數字或公式。
- 日期欄 `A, B` 寫入 Python `date` 或 `datetime`，數字格式 `yyyy-mm-dd`。
- 股數欄 `G, J` 為整數數值；價格／金額／比例為數值；`Decimal` 在序列化到 Excel 前要按欄位精度確定性轉換，原始精確 Decimal 仍保留於資料庫與 audit。
- 未賣欄寫 `None`，絕對不寫 `"-"`、`"未賣出"`、`"N/A"` 這種文字進數值欄。
- 若來源文字以 `=`, `+`, `-`, `@` 等可能被 Excel 解讀為公式的符號起頭，強制當純文字處理；禁止任何來源輸入變成可執行 Excel 公式。
- 預設 A1:W1 篩選／凍結首列、簡單字型和合理欄寬；不需要原 Excel 的底部 summary。
- 檔名：`交易明細_2026-11-20_17-50-00.xlsx` 這類秒級時間戳（格式示意；實際執行時取系統本地時間）。若同秒重名附加 `_01` 等，不覆蓋。
- 完成前重開輸出的 `.xlsx` 驗證：工作表、欄序、資料列數、欄位型別、公式數量（V1 應為 0）、總計列數（必為 0）、保留前導零的股票代號。

### 8.4 計算欄預設採值，不依賴舊公式

- `P/Q/R/S` 用 Python 在報表投影時算好，寫數值以便不依賴 Excel 自動重算。
- 若日後追加 Excel 原生計算公式模式，需專門版本與測試，**不得複製舊版底部 SUM 或不安全的共享公式**。
- `R=Q−P`、`S=R/P` 的公式定義僅作業務意義解釋；V1 存進 Excel 的是經驗證的數值，不是公式字串。

## 9. 統計報表與明細分離

- V1 `report detail` 只輸出 `detail.xlsx`、`audit.json`、`exceptions.csv`（及必要 `detail_index.csv`）。
- P1 才加入 `report stats`，讀取 `trades / fifo_allocations` 並輸出另一個 Excel `交易統計_時間.xlsx`。
- 統計維度：期間、帳戶、券商、股票代號與幣別。已實現損益、未實現持股數與費用應清楚定義；不能拿各個分段報表列的金額做隱含加總來代替正式的交易稽核。
- 不跨幣別無匯率加總；統計報表可以有合計列，**但明細報表嚴格沒有**。

## 10. CLI 介面約定

以下為設計規格，需由 Agent 實作，不代表現有指令已可執行：

```powershell
# 資料庫初始化
uv run python -m backend.cli db init --db data/trading.db

# 預覽檔案與欄位映射（不入庫）
uv run python -m backend.cli import preview --file "input/Statement (2).xls" --profile statement_html_v1

# 玉山真 XLSX 預覽（不入庫；現股＋現沖皆應通過類型驗證）
uv run python -m backend.cli import preview --file "input/玉山.xlsx" --profile esun_xlsx_v1

# 入庫：每批指定券商與帳戶
uv run python -m backend.cli import apply --file "input/Statement (2).xls" --broker "群益" --account "main" --profile statement_html_v1

# 玉山入庫（現股 CASH＋現沖 DAY_TRADE；正式驗收前請用臨時 DB）
uv run python -m backend.cli import apply --file "input/玉山.xlsx" --broker "玉山" --account "main" --profile esun_xlsx_v1 --db data/tmp_esun.db

# 執行 FIFO，將配對版本保存 SQLite
uv run python -m backend.cli match fifo --account "main"

# 產生純交易明細，不包含底部總計
uv run python -m backend.cli report detail --account "main" --output-dir output

# 需要時才允許產生標記 DRAFT 的未完成結果
uv run python -m backend.cli report detail --account "main" --allow-partial --output-dir output

# 稽核與本機備份
uv run python -m backend.cli audit --account "main"
uv run python -m backend.cli db backup --output-dir data/backups
```

設計約定：`--db` 可由環境變數 `TRADING_DB_PATH` 替代，但程式不得直接寫死使用者的 Windows 帳戶資料夾；任何會修改 DB 的 CLI 命令都要顯示異動摘要。

## 11. ACID、備份與資料保護

- 啟動每個 SQLite connection 設 `PRAGMA foreign_keys = ON`；開啟 WAL（若檔案系統相容），設定合理的 `busy_timeout`。
- 匯入批次採單個 transaction 或明確多階段狀態機；未完整驗證不得顯示成功入庫。
- 配對 run 一次版本化寫入，所有 allocations／issues 一致提交，錯誤回滾，不能覆蓋舊 run。
- 報表先寫暫存檔，驗證完才命名成正式 Excel；阻擋性例外僅可產生 `DRAFT`。
- 對 SQLite 使用 `sqlite3.Connection.backup()` 或 `VACUUM INTO` 做一致性備份；WAL 模式使用中不要把單純複製 `.db` 當成可靠備份方法。
- `.gitignore` 至少包含：`data/`、`input/`、`output/`、`*.db`、`*.db-wal`、`*.db-shm`、`.env`、`*.xlsx` 真實資料（若要提交測試小樣本須放專用去識別 fixtures 並例外明示）。
- 對個人交易資料、帳戶資訊、來源附件，預設只在本機存放，不上傳任何外部服務。

## 12. 驗證矩陣／測試案例

| Test ID | 測試條件 | 預期結果 |
|---|---|---|
| ING-01 | 參考檔是 HTML 內容但副檔名 `.xls` | 以 HTML parser 處理；65 筆、22 買、43 賣 |
| ING-02 | 兩筆「總合」列 | 排除，不當作交易 |
| ING-03 | UTF-8 BOM／CP950 的 CSV | 正確解析；未知編碼報錯 |
| ING-04 | 真正的 XLS、XLSX | 成功讀取並映射同一 canonical schema |
| ING-05 | 玉山 XLSX：非首列表頭＋四種交易類型 | 結構重塑成功；現股／現沖皆可辨識 |
| ING-06 | 玉山：日期列繼承＋次列代號 | 成交列取得正確日期；代號為正整數字串 |
| ING-07 | 玉山：小計／頁尾／說明列 | 排除，不當作可入庫現股交易 |
| ING-08 | 玉山：來源核對（`recognized_*` vs 頁尾） | **僅**四種已支援類型（含現沖）計入筆數／價金／手續費／交易稅；與頁尾一致則 `matched=true`。未支援候選列不計入；頁尾含未支援時 `matched=false`（預期，非整批失敗） |
| NORM-01 | 股票代碼有前導零 | DB、XLSX 均保留文字原樣 |
| NORM-02 | 千分位、Decimal 金額、小數價 | 不透過 float 計算 |
| NORM-03 | 未支援交易類型、日期錯誤 | 進例外而非默默納入 FIFO |
| NORM-04 | 玉山次列負數代號（如 `-4971.0`） | 正規化為文字 `4971`，無科學記號／小數點殘留 |
| NORM-05 | 現沖買／賣正規化 | `trade_type=DAY_TRADE`；side BUY／SELL；手續費／稅保留來源值 |
| DB-01 | 同帳戶同檔重匯入 | 第二次新增 0 筆交易 |
| DB-02 | 相同條件真實兩筆成交 | 不因欄位相同就誤刪 |
| DB-03 | 非法寫入、交易中途故障 | 交易回滾；既有資料完整 |
| FIFO-01 | BUY 1000，SELL 400 | 配對 400、剩餘 600 |
| FIFO-02 | BUY 1000+500，SELL 1200 | 配對 1000+200、剩餘 300 |
| FIFO-03 | 買進早於多次賣出 | 依順序配對、不超賣 |
| FIFO-04 | SELL 在所有可用 BUY 前 | 未匹配例外，不配對未來 BUY |
| FIFO-05 | 同日無可信先後且影響配對（**CASH**） | `ORDER_AMBIGUITY`，不得宣稱完成 |
| FIFO-06 | 不同帳戶、股票、幣別 | 絕不跨組配對 |
| FIFO-07 | 同日無序 DAY_TRADE（含先賣後買） | 當日相互 FIFO 配平；股數守恆；不標 ORDER_AMBIGUITY |
| FIFO-08 | DAY_TRADE 與跨日／同日 CASH 並存 | 現沖不消耗 CASH lot；CASH 不消耗 DAY_TRADE lot |
| FEE-01 | 一筆 BUY 被拆 3 段 | 該 BUY 的費用只在第一段 |
| FEE-02 | 一筆 SELL 配對 2 個 BUY | 該 SELL 手續費與交易稅只出現一次 |
| FEE-03 | source gross 與 price×qty 有合法尾差（`|diff|≤1`） | 各片段先 `TRUNC(qty×unit_price)`；容許內調最後片段後合計＝來源總額；不動費用；禁止比例／餘額法 |
| FEE-04 | 部分配對賣出（含殘量） | 已配對價金＋未配對殘量價金＝原始價金（經 §7.3）；主明細已配對列不得吃下全額 |
| FEE-05 | 收入含利息 | `income = sell_gross − commission − tax − interest`；息僅第一賣出費用片段 |
| FEE-06 | `|difference| > 1` | 不自動補差；保留截斷結果；`AMOUNT_CONSERVATION_OUT_OF_TOLERANCE`；該筆守恆失敗 |
| REP-01 | 明細輸出 A～W | 23 欄名、欄型別正確 |
| REP-02 | 有 10 筆片段 | 恰好 1 列標題 + 10 列明細；沒有第 12 列總計 |
| REP-03 | 無資料 | 只有表頭；沒有 `查無資料` 資料列 |
| REP-04 | 尚未賣出 | 賣方欄與損益均空白，而不是文字 `-` |
| REP-05 | 不含 Excel | Python 可獨立輸出、數值已計算 |
| REP-06 | 來源有可疑公式文字 | 當純文字，不插入可執行 Excel 公式 |
| REP-07 | 檔案同秒輸出 | 不覆寫既有檔案，附加唯一流水號 |
| AUD-01 | 阻擋性例外 | 正式版不可成功；`--allow-partial` DRAFT+例外 |
| AUD-02 | SQLite 備份與還原 | 可 `integrity_check` 並核對交易筆數／配對結果 |
| AUD-03 | 重新執行同版本 FIFO | 配對結果可重現、舊 run 不遭覆寫 |
| AUD-04 | 未配對賣出殘量 | 配套明細標 `UNMATCHED_SELL`；exceptions／audit 含 matched/unmatched qty／gross；未配對無虛構損益 |
| AUD-05 | 部分配對 W 備註 | 第一片段註記費用全額落點與殘量；本列損益非完整原始交易損益 |
| AUD-06 | 價金超容許差 | exceptions／audit 含 `AMOUNT_CONSERVATION_OUT_OF_TOLERANCE` 必填欄；守恆表輸出原始／截斷合計／difference／調整／最終／逐筆結果 |

### 12.1 必要測試隔離

- 單元與整合測試使用 `tmp_path` 的臨時 SQLite 與合成交易資料，不使用真實帳戶或原始附件提交到 Git。
- 原始提供的附件可於本機進行**手動驗收**；不要上傳或嵌入公開測試 fixtures。
- 比對報表時不可只檢查數值；還要檢查 `cell.data_type`、日期格式、股票代號、空白與「不存在合計列」。

## 13. Cursor Agent 實作順序與完成定義

### Milestone A — DB + Import

1. 建立 PRD／SPEC 對應的專案目錄與 `pyproject.toml`。
2. Alembic migration 建好完整 schema 和約束；能初始化、備份、檢查 DB。
3. Parser/Normalizer 及 profile 匯入完成；以附件進行 65 筆交易的手動驗收。
4. `pytest` 覆蓋基本格式、去重、錯誤回滾、Decimal 與來源追溯。

### Milestone B — FIFO

1. 先以純函式完成 FIFO 配對，測試一買多賣與一賣多買。
2. 明確處理來源次序不足、期初庫存及未匹配；不能偷偷補庫存。
3. 加入版本化 `allocation_runs` 與原子入庫及全部守恆測試。

### Milestone C — Detail Report

1. `detail_projector` 產生 23 欄 `DetailRow`，一次性費用落點穩定。
2. 新建 XLSX，不讀舊 Excel 統計表作為輸出底稿。
3. 列數／數值型別／日期型別／不含合計列／報表雜湊／例外報告通過。
4. 實際可透過 CLI 一次處理「匯入 → 配對 → 報表」；錯誤回滾或產 DRAFT。

### Milestone D（P1）— Stats / UI

1. 與明細完全分開的 stats projector／stats.xlsx。
2. 如需 GUI，加入 Streamlit 本機 UI，不改變核心領域模型。

**Done Definition**：P0 所有測試通過、同資料重跑不重複入庫、FIFO 數量與來源費用守恆、明細無合計列且全列符合型別、重要異常清楚報告、原始檔未修改、離線免費可執行。Agent 在開始 coding 前應先列出未決政策並將不可判定情境安全列例外。

交付至 `master` 時另須遵守 [`docs/DEVELOPMENT_WORKFLOW.md`](../DEVELOPMENT_WORKFLOW.md)：TDD／本機 REGRESSION、GitHub CI（`.github/workflows/pytest.yml`）、Code Review、適用時的人工 UAT，以及使用者明確授權後才 Merge。技術 Done ≠ 流程完成。

## 14. 風險與明確限制

- 本次範例交易來源包含早於該批買進的賣出；若使用者尚未提供歷史持倉，正確結果可能是**部分未匹配**，不是程式錯誤。
- 明細參考舊檔 A～W，但**不承諾保留舊 Excel 公式／最後兩列加總**；此次重做的要求正是移除統計混入明細的設計。
- 費用不拆分可造成個別已售片段的損益分布與一般成本攤提法不同；本系統嚴格依使用者自訂對帳規則，並在 audit 保留解釋。
- 台幣不同券商可能有不同成交額與費用尾差；需要 profile + 明確政策，不能只靠 `price * quantity` 猜所有交易。
- Python 計算後輸出 Excel 數值時，需要測試 Excel 格式所能表示的有效精度；**來源 Decimal 字串及精確稽核值仍在 DB**。

## 15. 官方文件

- SQLite：https://www.sqlite.org/about.html
- SQLite 使用情境：https://www.sqlite.org/whentouse.html
- SQLAlchemy SQLite：https://docs.sqlalchemy.org/en/20/dialects/sqlite.html
- Alembic：https://alembic.sqlalchemy.org/
- python-calamine：https://pypi.org/project/python-calamine/
- openpyxl：https://openpyxl.readthedocs.io/
- uv：https://docs.astral.sh/uv/
- pytest：https://docs.pytest.org/

## 16. 品質開發流程（引用）

端到端品質流程、Agent 權限邊界、CI／UAT／Merge 條件見：

- [`docs/DEVELOPMENT_WORKFLOW.md`](../DEVELOPMENT_WORKFLOW.md)
- 測試方法：[`docs/test/TDD.md`](../test/TDD.md)
- 實際測試證據：[`docs/test/TDD_STATUS.md`](../test/TDD_STATUS.md)
- CI 實際設定：[`.github/workflows/pytest.yml`](../../.github/workflows/pytest.yml)

本 SPEC 的驗證矩陣（§12）與財務契約仍為技術驗收依據；流程文件只規定交付閘門，**不**修改 FIFO／費用／報表計算規則。

> 文件是設計文件，不是已執行的程式。未確認的券商交易規則不應被 Agent 擅自當成既定財務事實。
