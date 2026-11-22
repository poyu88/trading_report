# Coding Standards 一致性稽核報告

| 項目 | 內容 |
|---|---|
| 分支 | `docs/coding-standards-alignment` |
| 基準 Commit | `a770a82`（與 `origin/master` 同步後開支） |
| 稽核日 | 2026-11-22 |
| 範圍 | 規範文件、Cursor Rules、工具設定；**不含**財務演算法／CI／`pyproject.toml` 變更 |
| Ruff 版本 | `0.17.6`（唯讀 `check`／`format --check`；未 `--fix`） |

---

## A. 規範衝突對照矩陣

| 主題 | 來源 A | 來源 B／實際 | 衝突？ | 裁決／處理 |
|---|---|---|---|---|
| Python 版本 | `.python-version`／`requires-python>=3.11`／CI `3.11`／`py-env.mdc` | README／SPEC／`target-version=py311` | 無 | 維持 3.11+ |
| uv／專案根 | SPEC／README：根目錄 `uv sync`／`uv run` | **舊** `backend-rule.mdc`：`cd backend` | **有（過時）** | 本任務修正 Rule；依賴以 `pyproject.toml` 為唯一權威 |
| 依賴清單 | `pyproject.toml`／`uv.lock` | 舊 Rule 列 LLM／embedding 等 | **有（誤導）** | Rule **不**複製套件清單 |
| Commit 格式 | `commit-rule.mdc`：`類型：繁中` | 部分歷史 Conventional（如 `docs:`） | 已知事實 | **保留**現行規則；不改歷史 |
| Agent 權限／禁 Force Push | `DEVELOPMENT_WORKFLOW`／`dev-workflow-rule` | 各 Rule 一致 | 無 | 保留 |
| UAT 隔離路徑 | Workflow §2.8／`dev-workflow-rule` 4a | 實務文件一致 | 無 | 保留 |
| TDD 四階段 | `TDD.md` 含 REFACTOR | 口語常省略 REFACTOR | 輕微 | 以 `TDD.md` 為準 |
| Python Style／Docstring／Hints | **缺**集中權威 | SPEC／pyproject 僅部分 | **缺漏** | 新增 `docs/CODING_STANDARDS.md` |
| Ruff 設定 | `pyproject`：`line-length=100`、`target-version=py311`；**未設** `lint.select` | Ruff **0.16+** 預設已遠大於經典 `E4/E7/E9/F`；CI **未**跑 ruff | 現況落差 | 文件說明＋baseline；**本任務不改** `pyproject`／CI；僅提案 |
| Docstring 工具 | Standards 採 Google Style | 未設 pydocstyle／D 規則 | 待採納 | 規範先寫入 Standards；啟用 D 時再改工具 |
| Type Hints | 新碼部分有標註 | 無統一政策 | 缺漏 | Standards 規定新碼優先；不一次改全庫 |
| CI | `pytest.yml` 僅 pytest | SPEC 提及 `ruff check` | 文件可提建議 | **不改** workflow；見 §E |
| 財務／Decimal | PRD／SPEC 權威 | Style／Ruff 可能建議改寫 | 潛在 | Style **不得**改變財務結果；FURB157 等須人工審 |
| SPEC §3 目錄 | 寫 `docs/PRD.md`、`docs/SPEC.md` | 實際 `docs/prd/`、`docs/spec/` | **路徑過時** | 本任務修正路徑並加 Standards 連結 |
| Workflow §7 | 登記 backend-rule 待修 | 本任務修正後應更新 | 狀態過時 | §7 改為已修訂 |

**待決策（不自行覆蓋政策）**

1. 是否在 `pyproject.toml` **明確鎖定／擴充** `lint.select`（接受 0.17 擴大預設，或暫時釘住經典子集以漸進清理）。
2. 是否／何時把 Ruff 納入 GitHub CI（見 §E）。
3. 是否啟用 Google Docstring 的 Ruff `D` 規則（需另改工具設定與歷史碼）。

無財務契約、Git 權限或正式 DB 保護之實質政策衝突需改寫；上列為工具節奏決策。

---

## B. Coding Standards 採納理由

1. **單一風格權威**：避免 Agent 在 SPEC／Rules／口頭慣例間猜測 PEP 8、docstring、型別與 Ruff 期望。
2. **不雙重維護**：流程仍以 `DEVELOPMENT_WORKFLOW`；TDD 以 `TDD.md`；財務以 PRD／SPEC；依賴以 `pyproject.toml`；Standards 只規範「怎麼寫程式」。
3. **Google Docstring**：公開 API／服務／複雜財務計算可讀性優先；簡單私有 helper 不強制長文；與 Type Hints 互補。
4. **漸進**：新碼遵守；歷史碼依 Ruff baseline 分階段；**禁止**為全綠大量 `ignore` 或自動 `--fix` 改財務碼。

詳見 [`docs/CODING_STANDARDS.md`](../CODING_STANDARDS.md)。

---

## C. Cursor Rules 變更摘要

| 檔案 | 動作 |
|---|---|
| `.cursor/rules/backend-rule.mdc` | **重寫**：移除 LLM 範本與 `cd backend`；根目錄 uv；引用 CODING_STANDARDS；依賴指向 pyproject |
| `py-env`／`commit`／`tdd`／`dev-workflow` | **保留**；不做平行 Style Rule |

---

## D. Ruff Baseline（歷史現況）

### D.1 設定現況

- `[tool.ruff]`：`line-length = 100`、`target-version = "py311"`。
- **尚未**在專案中明確設定 `lint.select`／`extend-select`／`ignore`（「尚未明確擴充／鎖定」專案層規則集合）。
- **重要（相對舊文件）**：自 Ruff **0.16** 起，未設 `select` 時的**預設規則集已大幅擴張**（約 400+ 條，含部分 E／F／I／UP／B／FURB／RUF 等），**不再等同**經典 `select = ["E4","E7","E9","F"]`。文件禁止寫成「E／F 尚未啟用」；亦不可再假設「預設只有 E4／E7／E9／F」。

### D.2 `uv run ruff check .`（未 `--fix`）

| 指標 | 數值 |
|---|---|
| 總違規 | **222** |
| 可 `--fix` | 201（另 15 需 `--unsafe-fixes`） |
| 對照：僅 `--select E4,E7,E9,F` | **7**（F401×6、F841×1） |

| 規則 | 次數 | 備註 |
|---|---|---|
| FURB157 | 173 | 見下方 **D.2.1**（非整數金額字串如 `Decimal("0.01")` **不**在此規則範圍） |
| RUF015 | 8 | `list…[0]` → `next(...)` |
| UP007 | 6 | `Optional`／`Union` → `|` |
| F401 | 6 | unused import |
| I001 | 5 | import 排序 |
| UP035 | 5 | deprecated import |
| RUF010 | 4 | f-string 型別轉換 |
| UP006 | 3 | `List`/`Dict` → 內建泛型 |
| 其他（BLE001、SIM*、UP009、PIE810、F841、PLW1510、RUF059…） | ≤2 each | — |

主要落點：測試檔（如 `tests/test_fragment_gross_trunc.py` 等）、`hooks/`、`alembic/versions/`；業務 `backend/` 相對較少。

#### D.2.1 FURB157（官方定義對齊）

依 Ruff 規則 [`verbose-decimal-constructor`（FURB157）](https://docs.astral.sh/ruff/rules/verbose-decimal-constructor/)：

| 項目 | 內容 |
|---|---|
| 檢查什麼 | `Decimal` 建構子中**不必要的**字串字面值或 `float(...)` 轉型 |
| 典型誤用 | 整數寫成字串：`Decimal("0")`／`Decimal("1")` → 建議 `Decimal(0)`／`Decimal(1)`；或 `Decimal(float("Infinity"))` → `Decimal("Infinity")` |
| **明確不標記** | 為精度而加引號的浮點字串，例如 `Decimal("0.1")`、`Decimal("0.01")`（官方說明：比 `Decimal(0.1)` 更精確） |
| Fix | Ruff 標為幾乎皆可自動修（含 comment 時除外）；**本專案仍禁止對財務相關碼盲目 `--fix`** |

本庫實例：`backend/services/report_finance.py` 中 `Decimal("0.01")`（`TWOPLACES`）**不**觸發 FURB157；同檔 `Decimal("1")`（`AMOUNT_TOLERANCE`）**會**觸發。即使 auto-fix 在整數案例語意通常等價，財務模組與測試仍須**人工審查**後才改建構形式，以符合「Style／Ruff 不得改變財務結果／慣例」政策。

### D.3 `uv run ruff format --check .`

- **28** files would be reformatted；**46** already formatted。
- 本任務**未**執行 `ruff format`。

### D.4 建議分階段（僅提案；本任務不改 pyproject／CI）

| 階段 | 建議 | 目的 |
|---|---|---|
| Phase A | 本機對照現行預設 `ruff check`；清理安全的 F401／I001；**人工審** FURB157（整數字串 `Decimal("N")`；勿動精度字串） | 建立可重複 baseline 意識 |
| Phase B | 在 `pyproject` **明確** `lint.select` 或 `extend-select`（接受 0.17 預設並 ignore 少數，或暫釘經典子集）；評估 CI `ruff check` | 鎖定可重現規則 |
| Phase C | 評估 `ruff format` CI 與 Google `D` 規則 | 格式／文件字串一致 |

建議後續明確採納方向（在預設之上）：其餘 E、I、UP、B 的專案政策；再評估 D 與 format。**不得**為通過而預先大量 ignore 歷史違規。

---

## E. Ruff 與 GitHub CI（建議，未實施）

| 建議 | 原因 |
|---|---|
| **短期不強制**把 Ruff 加入 CI | 現有 222 違規／28 待格式化；直接擋 PR 會淹沒財務審查 |
| **中期**（Phase B 後）加獨立 job 或 pytest job 步驟跑 `ruff check`（可先 `--select` 窄集合） | 防止新碼回退；與 pytest 權限模型一致（`contents: read`） |
| **勿**在未授權下改 `.github/workflows/pytest.yml` | 本任務邊界 |

---

## F. 驗證指令紀錄（實際執行；禁止捏造）

時點分兩段：**不得**用後段結果回填或竄改前段歷史列。本機 pytest ≠ GitHub CI ≠ 人工 UAT。

### F.0 PR 建立前（歷史；凍結）

檢查時點：PR／GitHub CI 尚未存在之時。驗證 Commit 基準為 `79cd5d4`（開支 `a770a82`）。`f56cae3` 為後續文件補正，**未**重跑並改寫本段 pytest 基準。

| 維度 | 結果 | 說明 |
|---|---|---|
| 驗證 Commit | `79cd5d4`（`doc：對齊 Coding Standards 與修正 backend-rule`） | 開支基準 `a770a82` |
| **本機** pytest | `uv run pytest -q` → **120 passed** in **56.35s**（exit 0；約 2026-11-22 實作當次） | **僅本機 REGRESSION**；**≠** GitHub CI Success |
| **本機** Ruff check | `uv run ruff check .`（未 `--fix`）→ **Found 222 errors**；201 fixable／15 unsafe | **歷史 baseline**；非本次文件變更引入 |
| **本機** Ruff format | `uv run ruff format --check .` → **28** would be reformatted，**46** already formatted（實作當次；未執行 format） | 同上 |
| 補正當次複核（文件修正、當時仍未 Commit） | `ruff check` 仍 **222**；`format --check` 報 28／**48** | 「already formatted」多 2：工作樹未追蹤 `scripts/*.py` 被掃到；**不**改寫上列 baseline，亦**不**視為 CI |
| GitHub Actions（本分支，當時） | `gh run list --branch docs/coding-standards-alignment` → **空** | 當時尚無對 `master` 的 PR；純推功能分支不觸發 `pytest.yml` |
| GitHub CI（當時） | **無對應 run** | **PR 建立前**真實狀態；不得以本機 pytest 冒充 CI |
| `git diff --check` | 通過（無 whitespace error 報告） | 實作當次 |
| 正式 DB／未追蹤保留 | 未寫入 `data/trading.db`；保留 `.cursor/plans/`、`esun_local_changes.patch`、`scripts/` | 邊界遵守 |

### F.0b PR／CI 後續驗證（新增；不覆寫 F.0）

| 維度 | 結果 | 說明 |
|---|---|---|
| PR | [#8](https://github.com/poyu88/trading_report/pull/8) — `doc：對齊 Coding Standards 與修正 backend-rule` | `docs/coding-standards-alignment` → `master` |
| Reviewed／公開 HEAD | `f56cae3`（`doc：補正 Standards 稽核紀錄與 Rule 連結`） | 含 backend-rule 連結、FURB157、§F 初版補正 |
| GitHub Actions Run | [`45028205176`](https://github.com/poyu88/trading_report/actions/runs/45028205176) | 由 PR 觸發 |
| **GitHub CI** | Python CI／**pytest：SUCCESS**（job 約 2026-11-22T13:35:11Z 完成） | **≠** 本機 pytest；**≠** 人工 UAT |
| 獨立 Code Review | **PASS WITH NOTES**（PR 註解；P2：§F 時點區分、§7.2 驗收具體化） | 本段與 Standards §7.2 補正即回應該 Notes |
| Ruff 全庫 | 仍為歷史債務（baseline **222**） | **禁止**宣稱 Ruff 全綠 |

### F.1 新碼 vs 歷史 Ruff 違規（在 222 項下如何區分）

全庫 **222** 為**已知歷史債務**，記錄於本檔 §D；**不**要求文件／Rules 變更一次清零，也**不得**用「全庫未全綠」否定新規範生效。細節以 [`docs/CODING_STANDARDS.md`](../CODING_STANDARDS.md) §7.2 為準。

| 判斷對象 | 通過標準 | 不作為阻擋的理由 |
|---|---|---|
| 純文件／Cursor Rules（本任務） | 無 Python 業務 diff；本機 pytest 未因本變更變紅；有 PR 後另以 GitHub CI 核對 | 既有 222／28 format |
| **新增** Python 檔 | 原則上 `ruff check <path>` **通過**；例外須記錄規則碼、原因、人工審查 | 其他檔歷史違規 |
| **修改**既有 Python 檔 | 以**新增診斷的檔案位置＋規則代碼**判定；**禁止**只憑違規總數不變宣稱無新增 | 同檔未改動行上的舊違規 |
| 宣稱「Ruff 全綠」 | **禁止**，除非另任務清理並更新 baseline | — |

---

## G. 權威關係（定稿）

| 職責 | 唯一正式來源 |
|---|---|
| 端到端流程／權限／UAT／Merge | `docs/DEVELOPMENT_WORKFLOW.md` |
| Python 風格／Docstring／Hints／Ruff 策略 | `docs/CODING_STANDARDS.md` |
| TDD 方法 | `docs/test/TDD.md` |
| 業務規則 | `docs/prd/PRD.md` |
| 技術／財務契約 | `docs/spec/SPEC.md` |
| 依賴與工具鎖定 | `pyproject.toml`／`uv.lock` |
| 實際 CI 行為 | `.github/workflows/pytest.yml` |
| Agent 強制摘要 | `.cursor/rules/*.mdc`（只連回上述來源） |

衝突依職責裁決；**禁止**「新檔一律優先」。財務／Git／資料安全實質衝突 → 待決策，不自行覆蓋。
