# trading_report

本機股票交易正規化、FIFO 配對與明細報表系統（Database-first）。

## 環境

- Python 3.11+
- 套件管理：`uv`（勿用 pip／poetry）

在專案根目錄操作：

```powershell
cd c:\Users\billh\python_test\trading_report
uv sync
uv run pytest
```

## 使用方式

### 1. 準備來源檔

把券商匯出檔放到 `input/`，例如：

```powershell
Copy-Item "c:\Users\billh\OneDrive\桌面\群益.xls" "input\群益.xls"
```

真實對帳單請放 `input/`，勿提交至 Git。

### 2. 標準流程（匯入 → 配對 → 報表）

```powershell
# 初始化資料庫
uv run python -m backend.cli db init --db data/trading.db

# （可選）先預覽，不入庫
uv run python -m backend.cli import preview --file "input/群益.xls" --profile statement_html_v1 --db data/trading.db

# 正式入庫（指定券商與帳戶標籤）
uv run python -m backend.cli import apply --file "input/群益.xls" --broker "群益" --account "main" --profile statement_html_v1 --db data/trading.db

# FIFO 買賣配對
uv run python -m backend.cli match fifo --account "main" --db data/trading.db

# 產出明細報表
# 若有「缺期初庫存」等阻擋例外，需加 --allow-partial（會標 DRAFT）
uv run python -m backend.cli report detail --account "main" --allow-partial --output-dir output --db data/trading.db
```

輸出會在 `output/`：

- `交易明細_DRAFT_*.xlsx`（或正式版 `交易明細_*.xlsx`）
- 同名的 `_audit.json`、`_exceptions.csv`

### 3. 常用輔助指令

```powershell
# 看稽核／例外摘要
uv run python -m backend.cli audit --account "main" --db data/trading.db

# 備份資料庫
uv run python -m backend.cli db backup --output-dir data/backups --db data/trading.db
```

### 3.1 玉山證券真 XLSX（`esun_xlsx_v1`）

```powershell
# 僅預覽（不入庫；建議先核對 65 筆類型驗證與來源合計）
uv run python -m backend.cli import preview --file "input\玉山.xlsx" --profile esun_xlsx_v1

# 若確認後要入庫：請指定臨時／測試 DB，勿直接寫入正式 data/trading.db，除非你已備份並知情
uv run python -m backend.cli import apply --file "input\玉山.xlsx" --broker "玉山" --account "main" --profile esun_xlsx_v1 --db data/tmp_esun.db

# 配對（現沖僅同日 DAY_TRADE pool；與解析錯誤分開看 exceptions）
uv run python -m backend.cli match fifo --account "main" --db data/tmp_esun.db
```

玉山格式重點：

- 日期列繼承、成交列下一列為股票代號（來源可能為負數，正規化為正整數字串）。
- `side`＝BUY／SELL；`trade_type`＝CASH（現股）／DAY_TRADE（現沖）。四種交易類型皆可入庫。
- 現沖僅在同日、同帳戶、同股票的 DAY_TRADE pool 內 FIFO（同日無序含先賣後買）；**不**消耗普通現股持倉。
- `YYYY/MM/DD 小計` 與頁尾說明排除；preview 會帶 `source_reconciliation` 與頁尾「資料筆數／價金／手續費／交易稅」核對。

### 注意事項

- 群益這份檔有「賣出早於本批買進」的部位，**正式報表會被擋**；目前請用 `--allow-partial` 產 DRAFT，或之後補核准的期初庫存再產正式版。
- 同一檔、同一帳戶重跑 `import apply` 不會重複入帳。
- `--account "main"` 只是帳戶標籤，之後查詢／配對／報表都要用同一個標籤。
- 真實對帳單與正式 `data/trading.db` 預設不納入 Git；自動化測試只用合成測資。

## 原則

- SQLite 為唯一交易事實來源；Excel 僅為可重建投影。
- 明細報表只有表頭＋明細列，**不含合計列**。
- 原始交易不因 FIFO 拆單而修改；費用不分攤，報表第一片段落點。
