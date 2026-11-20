# trading_report — TDD 測試指南

## 安裝位置

將 `tests/test_tdd_cli_contract.py` 放入本機 `trading_report/tests/`。

這是根據現有 `PRD.md`、`SPEC.md` 及提供的 README CLI 設計的 **黑箱契約測試**。不假設內部函式簽章，但要求主要 CLI、SQLite 資料表及報表規格符合文件。因無法取得你本機最新程式碼，目前**尚未在真實專案執行**；若程式採其他 CLI 參數或 profile 輸入約定，應由 Agent 調整測試適配層而非降低業務驗收標準。

## 執行方式（PowerShell）

```powershell
cd C:\Users\billh\python_test\trading_report
uv sync
uv run pytest tests/test_tdd_cli_contract.py --collect-only -q
uv run pytest tests/test_tdd_cli_contract.py -q -x --tb=short
uv run pytest tests/test_tdd_cli_contract.py -v
```

`-x` 第一個失敗便停止；修好後再執行全套。測試用 `tmp_path` 建立獨立資料庫與報表，不讀寫 `data/trading.db`、`input/`、`output/` 的真實資料；虛構的 HTML `.xls` 檔是在測試期間即時產生。

## 測試案例矩陣

| ID | 規格 | 期望 |
|---|---|---|
| 01 | 預覽不入庫 | `trades` 筆數保持 0 |
| 02 | HTML `.xls` 標準化 | 買賣轉 BUY/SELL；排除總合列；股票代碼 `0050` 保留 |
| 03 | 重複匯入 | 同檔同帳戶重跑仍只有一筆交易 |
| 04 | 真實重複成交 | 同日同價同量兩筆不被錯誤去重 |
| 05 | 來源完整性 | 匯入前後 SHA-256 不變 |
| 06 | FIFO 一賣多買、費用守恆 | 1000+500 買、1200 賣 → 1000+200 配對、300 未售；手續費只各出現一次 |
| 07 | FIFO 一買多賣 | 買 1000、賣 400+300 → 未售 300；買費只在首片段 |
| 08 | Excel Schema | 23 欄、僅明細列、日期型別、股數數值、代號文字、無公式無 SUM |
| 09 | 缺期初庫存 | 早於買進的 SELL 不配後買；正式版阻擋、DRAFT 有例外 |
| 10 | 帳戶隔離 | A 的買進不能替 B 的賣出配對 |
| 11 | 檔案名稱防覆寫 | 相同測資連續輸出兩次檔名不同且舊檔不變 |
| 12 | SQLite 備份 | `integrity_check = ok` 且交易筆數一致 |

## TDD 操作

1. **RED**：選一個尚未滿足的商業規則，先新增測試，執行並確認因該需求缺失而失敗。
2. **GREEN**：只寫最小修改讓該測試通過，不能為了綠燈刪除/弱化測試。
3. **REFACTOR**：改善結構但維持所有測試通過。
4. **REGRESSION**：每次提交前跑整套既有 `pytest` 與這份契約測試。

既有功能開發完後才補測試，嚴格來說叫 **特徵化／回歸測試**，不是當初開發的 TDD；從下一個新增需求起，堅持先 RED 才符合 TDD。

## 建議首個 RED 案例：防止跨帳戶 FIFO

```powershell
uv run pytest tests/test_tdd_cli_contract.py::test_10_fifo_never_matches_buys_from_different_accounts -v -x
```

如果此測試紅燈，先判斷是：
- 測試合成 HTML 格式和 parser 不相容（須修 fixture、不是業務失敗），或
- 系統真的跨帳戶匹配／未阻擋報表（業務失敗，才進入 RED→GREEN）。

## 建議的更細粒度 unit tests（下一輪）

- `tests/test_fifo.py`：直接測 FIFO 的 1000+500→1200、日期順序與未售量，`Decimal` 與純函式，避免為每個小變化都啟動 CLI。
- `tests/test_fee_once.py`：一次性費用 20、10、18、36 在段落中只出現一次；核對成本與收入。
- `tests/test_normalizer.py`：`0050` 保持字串、CP950/UTF8、千分位與小數精度、未知交易類別。
- `tests/test_report_schema.py`：股票代號文字、日期/金額數值、空值、文字公式注入、無統計列。
- `tests/test_db_transactions.py`：原子性回滾、外鍵及中途錯誤不污染既有紀錄。

測試的 `--account` 是合成帳戶標籤；不得把真實券商帳戶、密碼、交易紀錄提交到測試 fixtures 或 GitHub。
