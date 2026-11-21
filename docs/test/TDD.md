# trading_report — TDD 規範（唯一正式來源）

本文件是本專案 **TDD 政策與操作標準的唯一正式來源**。

| 文件 | 職責 |
|---|---|
| `docs/test/TDD.md`（本檔） | 完整 TDD 政策、流程、契約矩陣、執行方式 |
| `docs/DEVELOPMENT_WORKFLOW.md` | 端到端品質流程（PRD→TDD→Commit→Push→PR→CI→Review→UAT→Merge） |
| `.cursor/rules/tdd-rule.mdc` | 強制 Agent 閱讀、遵守及執行本政策 |
| `.cursor/rules/dev-workflow-rule.mdc` | 強制 Agent 遵守端到端流程與權限邊界 |
| `docs/test/TDD_STATUS.md` | 實際測試結果、Commit、稽核證據 |
| `tests/test_*.py` | 可執行測試案例 |

Agent 與開發者不得另建平行指南重複維護相同內容。若本檔與 `tdd-rule.mdc` 衝突，以本檔為準並回報不一致處。
端到端交付（Push／PR／CI／UAT／Merge）以 `docs/DEVELOPMENT_WORKFLOW.md` 為準；本檔只規範測試方法，不授權 Agent 自行 Push 或 Merge。

---

## 1. 核心原則

所有新增功能、功能修改及 Bug 修正，必須遵循：

**RED → GREEN → REFACTOR → REGRESSION**

既有功能開發完後才補測試，嚴格來說叫 **特徵化／回歸測試**，不是當初開發的 TDD。從下一個新增需求起，必須先 RED 才符合本規範。

不得虛構 RED／GREEN／REFACTOR 歷史，不得削弱既有驗收斷言來換取綠燈。

---

## 2. 階段定義

### 2.1 RED

1. 選一個尚未滿足的商業規則，先新增或擴充測試。
2. 執行測試，確認失敗原因是「預期業務行為尚未實現」，而非 fixture／CLI 適配錯誤。
3. 記錄 pytest 失敗輸出（指令、失敗摘要）。
4. 先提交測試 Commit（若已使用 Git）。

若失敗是合成 HTML 與 parser 不相容，應先修正 fixture／適配層，**不得**把它當成業務 RED。

### 2.2 GREEN

1. 僅做讓該測試通過的最小實作。
2. 不得刪除或弱化測試斷言。
3. 確認目標測試通過。
4. 提交實作 Commit。

### 2.3 REFACTOR

1. 改善程式結構與品質，但不得改變既有業務行為。
2. 相關測試必須保持通過。
3. 記錄重構內容與結果。

### 2.4 REGRESSION

1. 提交前執行完整：`uv run pytest -q`。
2. 必須全部通過才能宣稱完成。
3. 更新 `docs/test/TDD_STATUS.md`（含真實輸出摘要與 Commit）。

---

## 3. 安全與隔離

- 使用 `tmp_path` 與合成交易資料。
- 不得讀寫正式 SQLite（`data/trading.db`）。
- 不得修改真實交易來源檔（`input/` 真實對帳單）。
- 不得污染正式 `output/` 報表。
- 不得把真實券商帳戶、密碼、交易紀錄提交到 fixtures 或 Git。
- 測試用的 `--account` 僅為合成帳戶標籤。

---

## 4. 執行方式（PowerShell）

```powershell
cd C:\Users\billh\python_test\trading_report
uv sync
uv run pytest tests/test_tdd_cli_contract.py --collect-only -q
uv run pytest tests/test_tdd_cli_contract.py -q -x --tb=short
uv run pytest -q
uv run pytest -v --tb=line
```

- `-x`：第一個失敗便停止；修好後再跑全套。
- 契約與單元測試皆以 `tmp_path` 建立獨立資料庫與報表，不觸碰正式資料。
- 合成 HTML `.xls` 於測試期間即時產生或使用 `tests/fixtures/` 去識別樣本。

---

## 5. CLI 契約測試矩陣

檔案：`tests/test_tdd_cli_contract.py`

這是依 `docs/prd/PRD.md`、`docs/spec/SPEC.md` 與 README CLI 設計的 **黑箱契約測試**：不假設內部函式簽章，但要求主要 CLI、SQLite 資料表及報表規格符合文件。若實作採其他 CLI 參數或 profile 約定，應調整測試適配層，**不得降低業務驗收標準**。

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

現況：上述契約與其他單元／整合測試合計原 **34 項**特徵化／回歸安全網；自 `esun_xlsx_v1` 起另有 TDD 新增測試，全量見 `TDD_STATUS.md`（例如 43 passed）。原 34 項的存在**不構成**歷史 TDD 完成證明。

---

## 6. 建議的下一輪 RED 與細粒度單元測試

### 6.1 建議首個新需求 RED 案例：防止跨帳戶 FIFO

```powershell
uv run pytest tests/test_tdd_cli_contract.py::test_10_fifo_never_matches_buys_from_different_accounts -v -x
```

若此測試紅燈，先判斷：

- 測試合成 HTML 與 parser 不相容 → 修 fixture（非業務失敗）；或
- 系統真的跨帳戶匹配／未阻擋報表 → 業務失敗，才進入 RED→GREEN。

（註：該案例目前已綠燈且屬回歸基準；新需求應另寫會因缺口而失敗的測試。）

### 6.2 建議細粒度 unit tests

- `tests/test_fifo.py`：FIFO 1000+500→1200、日期順序與未售量；`Decimal` 與純函式。
- `tests/test_fee_once.py`：一次性費用在段落中只出現一次；核對成本與收入。
- `tests/test_normalizer.py`：`0050` 保持字串、CP950/UTF8、千分位與小數精度、未知交易類別。
- `tests/test_report_schema.py`：股票代號文字、日期/金額數值、空值、文字公式注入、無統計列。
- `tests/test_db_transactions.py`：原子性回滾、外鍵及中途錯誤不污染既有紀錄。

（多數檔案已存在並納入 34 項回歸；新增 SPEC 缺口時必須先 RED，見 `TDD_STATUS.md` §5。）

---

## 7. 狀態紀錄要求

每次完成 RED／GREEN／REFACTOR／REGRESSION 後，更新 `docs/test/TDD_STATUS.md`：

- **RED**：失敗測試名稱、pytest 指令、失敗原因、測試 commit SHA。
- **GREEN**：最小變更摘要、功能 commit SHA；禁止刪減斷言。
- **REFACTOR**：結構改善說明、commit SHA；之後全量 pytest 必須通過。
- **REGRESSION**：全量 `uv run pytest -q` 結果（通過數／失敗數）。

回歸基準 Commit（現有功能入庫、非 TDD 完成）見 `TDD_STATUS.md`（`cf4e68e`）。

---

## 8. 與 SPEC／開發流程的關係

業務驗收條件以 `docs/spec/SPEC.md` §12 驗證矩陣為準。本檔規範「如何用 TDD 交付」；覆蓋缺口與實際通過狀態以 `TDD_STATUS.md` 為準，不得在狀態檔虛構通過。

本機 REGRESSION（`uv run pytest`）通過後，仍須依 `docs/DEVELOPMENT_WORKFLOW.md` 完成 GitHub CI、Code Review 與（適用時）人工 UAT，才可合併。**本機 pytest ≠ GitHub CI ≠ 人工 UAT。**
