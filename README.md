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

### 注意事項

- 群益這份檔有「賣出早於本批買進」的部位，**正式報表會被擋**；目前請用 `--allow-partial` 產 DRAFT，或之後補核准的期初庫存再產正式版。
- 同一檔、同一帳戶重跑 `import apply` 不會重複入帳。
- `--account "main"` 只是帳戶標籤，之後查詢／配對／報表都要用同一個標籤。

## 原則

- SQLite 為唯一交易事實來源；Excel 僅為可重建投影。
- 明細報表只有表頭＋明細列，**不含合計列**。
- 原始交易不因 FIFO 拆單而修改；費用不分攤，報表第一片段落點。
