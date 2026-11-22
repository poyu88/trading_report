# trading_report — Coding Standards（Python 風格唯一正式來源）

本文件是本專案 **Python 程式碼風格與可維護性標準** 的唯一正式來源。
流程、財務契約與 TDD 方法不在此重複維護。

| 文件 | 職責 |
|---|---|
| `docs/CODING_STANDARDS.md`（本檔） | 風格、Docstring、Type Hints、錯誤／日誌、測試程式風格、Ruff 策略 |
| `docs/DEVELOPMENT_WORKFLOW.md` | 端到端流程、權限、CI／Review／UAT／Merge |
| `docs/prd/PRD.md` | 產品與業務規則 |
| `docs/spec/SPEC.md` | 技術規格、schema、FIFO／費用／報表契約 |
| `docs/test/TDD.md` | TDD 方法（RED→GREEN→REFACTOR→REGRESSION） |
| `pyproject.toml`／`uv.lock` | 依賴與工具設定的**唯一權威** |
| `.github/workflows/pytest.yml` | 實際 CI 行為 |
| `.cursor/rules/*.mdc` | 強制 Agent 遵守上述來源的精簡指示 |

Agent 與開發者不得另建平行「風格指南」重複維護相同內容。
若本檔與 Cursor Rule 衝突，以本檔為準並回報不一致處。
財務數字、FIFO、TRUNC、報表欄位契約以 PRD／SPEC 為準；本檔**不得**被解讀為可放寬財務斷言。

---

## 1. Python 基本規範

- **版本**：Python **3.11+**（與 `.python-version`、`requires-python`、CI 對齊）。
- **風格基準**：遵循 PEP 8；文件字串精神對齊 PEP 257；以 **Ruff** 作為本機靜態檢查／格式工具。
- **行寬**：100（見 `pyproject.toml` `[tool.ruff] line-length`）。
- **命名**：模組／函式／變數 `snake_case`；類別 `PascalCase`；常數 `UPPER_SNAKE`；公開 API 名稱應穩定、可搜尋。
- **模組職責**：單一模組單一關注點；CLI／服務／domain／DB／報表分層勿混雜副作用。
- **依賴**：
  - **套件與版本以根目錄 `pyproject.toml`／`uv.lock` 為唯一權威**；勿在 Rules／本檔複製完整清單。
  - 僅使用 `uv add`／`uv add --dev` 新增；禁止 pip／poetry／conda／手動 venv。
  - 不得在沒有明確需求時新增依賴。
- **執行**：一律在專案**根目錄** `uv sync`／`uv run …`（不要假設需 `cd backend`）。

---

## 2. Google Style Docstring

本專案公開與複雜邏輯採用 **Google Style** docstring（Args／Returns／Raises／Yields／Note 等區塊）。

### 2.1 何時必備

- 套件／模組的公開 API
- 重要類別與服務函式（匯入、FIFO、配置、報表投影等）
- 複雜財務計算、守恆檢查、非直覺的會計／排序政策

### 2.2 何時可不寫長 docstring

- 名稱已自明的簡單私有 helper（如 `_group_key`）
- 僅轉呼叫、無額外契約的薄包裝
- 與 Type Hints 完全重複且無行為說明價值時，避免堆砌

### 2.3 與 Type Hints

- Docstring 說明**語意、單位、不變量、副作用**；型別以 annotations 為準，避免在 Args 重複寫 `str`／`int` 除非需補充約束（例如「台股股數、非負整數」）。

### 2.4 工具設定

- 本政策**先寫入本檔**；**尚未**在 `pyproject.toml` 啟用 Ruff `D`（pydocstyle）規則。
- 待專案決定啟用 D 規則時，再一併設定 `pydocstyle.convention = "google"`（或同等）與分階段清理；**不得**為宣告本政策而在未授權任務中改工具設定。

---

## 3. Type Hints

- **新碼**優先完整標註參數與回傳型別。
- 對外服務、資料轉換、FIFO／配置、DB repository／session 操作優先完整。
- 避免無必要的 `Any`；寧可用 `Protocol`、`TypedDict`、具體型別或縮小的 `object`。
- 使用 3.10+ 語法偏好（如 `X | None`）；與既有碼並存時以可讀與一致性為先。
- **不**要求一次改寫全庫舊函式；改到該處時一併補齊。

---

## 4. 財務程式特殊規範（引用既有契約）

詳細演算法與欄位以 PRD／SPEC 為準。本檔僅強調風格層硬性約束：

- 金額／單價運算使用 `Decimal`；**禁止**用 `float` 或 SQLite `REAL`／`SUM(CAST…AS REAL)` 產生財務結果。
- **Style／Ruff／formatter 不得改變財務結果**。對 Ruff 建議（含 [FURB157](https://docs.astral.sh/ruff/rules/verbose-decimal-constructor/)：不必要的整數字串如 `Decimal("1")`→`Decimal(1)`；**不**標記精度字串如 `Decimal("0.01")`）必須人工審查後才改；不確定時維持現狀並開待決策。禁止對財務相關碼盲目 `ruff check --fix`。
- 不得為通過 linter 而放寬測試財務斷言或刪除守恆檢查。
- 真實對帳單、正式 DB、正式報表不得進入自動化測試或 Commit。

---

## 5. 錯誤處理與日誌

- 捕捉例外時保留上下文（鏈式 `raise … from e` 或明確記錄原因）；**禁止**裸 `except:`／靜默吞錯。
- 對預期業務例外使用明確型別；不要用過寬的 `except Exception` 掩蓋程式錯誤（除非在邊界做統一轉換且有紀錄）。
- 日誌與錯誤訊息**禁止**輸出 Token、密碼、`.env` 內容；避免不必要的完整真實交易明細。

---

## 6. 測試程式風格

- **TDD 流程**仍以 [`docs/test/TDD.md`](test/TDD.md) 為唯一權威；本節只規範測試碼可讀性。
- 測試名稱表達情境與期望（`test_<行為>_<條件>_<期望>` 或同等清晰命名）。
- 使用 `tmp_path` 與合成資料；不得讀寫 `data/trading.db` 或真實 `input/` 對帳單。
- Fixture 保持精簡；斷言應對準業務結果（數量、Decimal、例外碼），避免只斷「沒炸」。
- 財務相關測試不得為綠燈而削弱斷言。

---

## 7. Ruff 現況與漸進策略

### 7.1 現況（以 `pyproject.toml` 與 Ruff 0.17.x 為準）

- 已設定：`line-length = 100`、`target-version = "py311"`。
- **尚未**在專案層明確設定 `lint.select`／`extend-select`（「尚未明確擴充／鎖定」專案規則集合）。
- 未設 `select` 時，Ruff **0.16+** 仍會套用其**擴大後的預設規則集**（內含多類 E／F 及 I／UP／B／FURB 等；**不再**等同舊文件所寫的「僅 E4／E7／E9／F」）。敘述時禁止寫成「E／F 尚未啟用」。
- GitHub CI（`pytest.yml`）目前**只跑 pytest**，不跑 Ruff。
- Baseline 數字與分階段建議見 [`docs/audit/CODING_STANDARDS_ALIGNMENT.md`](audit/CODING_STANDARDS_ALIGNMENT.md)。

### 7.2 策略（新碼 vs 歷史違規）

全庫既有 Ruff 違規數以稽核報告 baseline 為準（撰寫時約 **222**）；屬**歷史債務**，不要求每次變更清零，也不得宣稱「未全綠＝新規範無效」。**不**要求本變更清除全部歷史違規。

| 對象 | 驗收條件 |
|---|---|
| **新增** Python 檔 | 原則上對該檔 `uv run ruff check <path>` **必須通過**。若有例外（例如暫時無法消除的規則），須在 PR／稽核紀錄寫明：**規則代碼**、原因、人工審查結論；財務相關建議一律先人工審，禁止盲目 `--fix` |
| **修改**既有 Python | 以本次變更是否**引入新的診斷**判定：比對變更檔上**新增**的（檔案路徑、列號區間、規則代碼）。**禁止**僅因全庫或單檔「違規總數相同／未上升」就宣稱沒有新增違規（避免新增與修復舊項互相抵銷）。未改動行上的舊違規不自動視為本變更失敗 |
| **純文件／Rules** | 不要求清歷史 Ruff；本機 pytest 回歸佐證未破壞行為；有 PR 時另以 GitHub CI（pytest）核對，三者不可互相替代 |
| 全庫 `ruff check .` 全綠 | 僅在另開清理任務並更新 baseline 後才可宣稱 |

- 不在未授權任務執行 `ruff check --fix`／`ruff format` 大批改寫歷史碼；財務相關修復仍須人工審查。
- 明確擴充或鎖定 `select`、啟用 format／D、以及是否納入 CI，屬**待決策**；實施時另開任務並遵守 DEVELOPMENT_WORKFLOW。

---

## 8. Code Review 與本標準

Review 結論格式遵循 `DEVELOPMENT_WORKFLOW`：`PASS`／`PASS WITH NOTES`／`FAIL`。
審查風格議題時以本檔為準；不得用風格意見覆寫財務契約。
