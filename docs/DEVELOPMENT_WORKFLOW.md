# trading_report — 品質開發流程（主文件）

本文件是本專案 **端到端品質開發流程** 的唯一正式來源。
財務規格、欄位契約與測試方法仍分別以 PRD／SPEC／TDD 為準；本檔只定義「如何把變更安全地送到 master」。
驗收誠信／四態以 [`AGENT_INTEGRITY.md`](AGENT_INTEGRITY.md) 為準；待驗證登記以 [`test/PENDING_DATA_VALIDATION.md`](test/PENDING_DATA_VALIDATION.md) 為準。
工程治理採用母版 `python-engineering-template` **`v1.1.0`**／`1.1.0-template`（見 [`STANDARDS_VERSION.md`](../STANDARDS_VERSION.md)）。

| 文件 | 職責 |
|---|---|
| `docs/DEVELOPMENT_WORKFLOW.md`（本檔） | PRD→TDD→Commit→Push→PR→CI→Review→UAT→Merge；風險導向隔離驗收 |
| `docs/AGENT_INTEGRITY.md` | 驗收誠信、四態、anti-gaming、反過度工程 |
| `docs/test/PENDING_DATA_VALIDATION.md` | 持久化待驗證事項（產品沿用擴充；含資料與工程治理 PENDING） |
| `docs/BACKUP_AND_ARTIFACT_POLICY.md` | 永久備份／暫存產物分類與 INDEX |
| `docs/CODING_STANDARDS.md` | Python 風格、Docstring、Type Hints、Ruff 策略（唯一風格權威） |
| `docs/prd/PRD.md` | 產品需求、業務規則、驗收案例 |
| `docs/spec/SPEC.md` | 技術規格、schema、FIFO／費用／報表契約、驗證矩陣 |
| `docs/test/TDD.md` | TDD 方法（RED→GREEN→REFACTOR→REGRESSION） |
| `docs/test/TDD_STATUS.md` | **實際**測試結果與 Commit／稽核證據（不得寫計畫中的通過） |
| `AGENTS.md` | 跨 Agent 精簡入口 |
| `STANDARDS_VERSION.md` | 母版採用版本、工具採用狀態、專案例外 |
| `.github/workflows/pytest.yml` | GitHub Actions CI 實際設定（並列 `lint`／`pytest` 兩 Job；以 YAML 為準） |
| `.cursor/rules/dev-workflow-rule.mdc` | 強制 Agent 遵守本流程的精簡規則 |
| `.cursor/rules/tdd-rule.mdc` | 強制 Agent 遵守 `TDD.md` |
| `.cursor/rules/commit-rule.mdc` | Commit message 格式 |
| `.cursor/rules/backend-rule.mdc` | uv／根目錄執行／指向 Coding Standards（依賴以 `pyproject.toml` 為準） |

Agent 與開發者不得另建平行「流程指南」重複維護相同內容。若本檔與 Cursor Rule 衝突，以本檔為準並回報不一致處（工程驗收層標 `PENDING`，不得靜默採寬鬆解釋）。

---

## 1. 核心流程

未來所有功能開發及 Bug 修復，原則上遵循：

```text
PRD / SPEC
    → TDD（RED → GREEN → REFACTOR → REGRESSION）
    → Git Commit
    → Git Push
    → Pull Request
    → GitHub CI
    → Code Review
    → UAT
    → Merge
```

說明：

- TDD 細節以 [`docs/test/TDD.md`](test/TDD.md) 為準；其中含 **REFACTOR** 階段。本流程圖保留 REFACTOR，與「RED→GREEN→REGRESSION」摘要並不衝突：REFACTOR 介於 GREEN 與 REGRESSION 之間，且不得改變既有業務行為。
- **本機 pytest 通過 ≠ GitHub CI Success ≠ 人工 UAT 通過**。三者各自獨立，不可互相替代。
- GitHub CI 內的 **Ruff lint** 與 **pytest** 是兩個不同品質門檻；任一失敗都須調查。Ruff 綠燈**不**代表可自動 Merge，也不取代 Code Review 或財務 UAT。
- 本機正式驗收＝**已採用**成熟工具**逐項**通過（各記 exit code 與工程四態），**無**自訂 Overall PASS 聚合器。
- 工程驗收四態：`PASS`｜`FAIL`｜`PENDING`｜`N/A`（定義見 [`AGENT_INTEGRITY.md`](AGENT_INTEGRITY.md)）。工具採用 `NOT_ADOPTED` ≠ `N/A`。

---

## 2. 各階段要求

### 2.1 PRD / SPEC

- 定義需求、業務規則、技術規格及驗收條件。
- 修改前先閱讀：
  - [`docs/prd/PRD.md`](prd/PRD.md)
  - [`docs/spec/SPEC.md`](spec/SPEC.md)
  - 欄位契約（SPEC §8 等）
  - 既有測試與 [`docs/test/TDD_STATUS.md`](test/TDD_STATUS.md)
- 規格變更採**增量修改**，不任意破壞既有契約（尤其財務、FIFO、費用、TRUNC／尾差、A～W 報表）。
- 未確認業務決策（PRD §11）不得由 Agent 自行假定。

### 2.2 TDD

完整政策見 [`docs/test/TDD.md`](test/TDD.md)。摘要：

| 階段 | 要求 |
|---|---|
| **RED** | 先建立可重現需求或 Bug 的失敗測試；失敗須來自「預期業務行為尚未滿足」 |
| **GREEN** | 最小必要實作；不得刪除或弱化驗收斷言 |
| **REFACTOR** | 可改善結構；不得改變既有業務行為；相關測試保持通過 |
| **REGRESSION** | 執行相關測試與完整 `uv run pytest -q`；更新 `TDD_STATUS.md` |

額外硬性規則：

- 保留真實測試輸出與必要證據（見 `TDD_STATUS.md`）：含適用之 Passed／Failed／Skipped／XFailed／XPassed 與 Exit Code。
- **不得**只為了通過測試而放寬財務斷言。
- 測資分層見 §2.2.1 與 [`AGENT_INTEGRITY.md`](AGENT_INTEGRITY.md) §2.2.2：日常／公開 CI 用合成或公開安全 fixture；經授權私人驗收須符合 Private Fixture Gate；**禁止**以正式 DB／正式報表／原始對帳單作為一般自動化測試的可寫入目標。
- 既有「先實作後補測」屬特徵化／回歸，不得偽稱為當次 TDD 完成。
- Pytest Exit Code `0` ≠ 所有案例／需求已通過；分層語意見 §4 與 Pending `VP-TR-004`。

### 2.2.1 測資與自動化邊界（三層）

| 層 | 允許 | 禁止 |
|---|---|---|
| **日常 TDD／公開 CI** | 合成測資、公開安全 Fixture、`tmp_path` 或其他適當隔離測試資料 | 載入私人交易資料；讀寫正式 DB |
| **私人資料驗收**（須 Owner 授權） | 經授權之 REAL_DERIVED、Golden Case 或其他可信私人測資之**隔離**自動化驗收 | 上傳私人資料至公開 Git／CI；錯誤訊息洩漏私人財務數值；繞過既有 Private Fixture Gate；缺測資時虛構 PASS |
| **正式資料** | （非一般自動化測試目標） | 未授權讀取／修改／複製正式交易 DB、正式報表、原始對帳單；將其作為一般自動化測試可寫入目標 |

私人資料驗收另須：gitignore／敏感保護、最小必要資料、隔離 DB／輸出路徑、可信且獨立的預期結果。缺少必要私人測資 → 對應需求維持 **`PENDING`**。不得以合成資料冒充真實資料驗收。**不得**修改既有 Private Fixture Gate 或產品測試程式（除非另授權）。

### 2.3 Git Commit

- 使用**功能分支**開發（勿直接在 `master` 上累積未審變更）。
- 將程式碼、測試與文件依合理範圍提交；Commit 應清楚描述修改目的。
- Commit message 格式遵守 [`.cursor/rules/commit-rule.mdc`](../.cursor/rules/commit-rule.mdc)。
- **不得**將下列內容加入 Commit：
  - 正式資料庫（如 `data/trading.db`）
  - 券商原始交易資料／真實對帳單
  - 機密資訊（Token、密碼、`.env`）
  - 無關檔案（本機計畫草稿、臨時 patch、個人筆記等，除非任務明確要求）
- **Agent 權限**：僅在使用者**明確授權**本任務建立本機 Commit 時才可 `git commit`；**不得**自行擴張至 Push、開 PR 或 Merge。

### 2.4 Git Push

- 原則上由**使用者親自執行**。
- Agent **不得**擅自使用個人 GitHub Token，或要求過大的 Repository 寫入權限來完成 Push。
- **Cursor Agent 禁止執行 Force Push**（含 `--force`／`--force-with-lease` 等改寫遠端歷史的推送）。
- **不得**因一般工作授權（含「請 Push」「請同步遠端」）而解除 Force Push 禁令。
- 如確實需要改寫遠端歷史，**須由使用者親自評估與操作**；Agent 可說明風險，但不得代為執行。
- 一般（非 force）Push 仍依使用者明確授權執行；未授權時 Agent 停在本機變更／文件審查階段。

### 2.5 Pull Request

- 原則上由**使用者建立 PR**。
- PR 應包含：
  - Summary（做了什麼、為什麼）
  - 變更範圍（檔案／模組）
  - 測試證據（本機 pytest／相關案例；連結或貼上摘要）
  - 風險（財務、資料、相容性）
  - 待驗收項目（UAT checklist）
- 目標分支原則上為 `master`。
- 若使用 Stack／相依分支，須先確認分支依賴與合併順序。
- Agent 未獲明確授權時，**不得**自行 `gh pr create` 或等同操作。

### 2.6 GitHub Actions CI

以 [`.github/workflows/pytest.yml`](../.github/workflows/pytest.yml) 為**唯一實際設定依據**（勿臆造未寫入 YAML 的步驟）。

目前實際行為（以 YAML 為準）：

| 項目 | 實際內容 |
|---|---|
| 觸發 | `push` → `master`；`pull_request` → `master`；`workflow_dispatch` |
| 權限 | `permissions.contents: read`（最小讀取） |
| Jobs | 並列 **`lint`（ruff）** 與 **`pytest`**（互不 `needs`；風格失敗不取消回歸測試） |
| 環境 | `ubuntu-latest`；Python **3.11**；`astral-sh/setup-uv`（pin commit） |
| 依賴 | 各 Job：`uv sync --locked --dev` |
| Lint | `uv run --locked ruff check .`（規則唯讀 `pyproject.toml`；不 `--fix`） |
| 測試 | `uv run --locked pytest -q` |
| Checkout | `persist-credentials: false`（避免步驟內遠端寫入） |

硬性規則：

- **不**使用個人 PAT 或不必要的 Secrets 跑此 workflow。
- CI **不得**自動 Push、修改正式資料或 Merge。
- CI Failure **必須先調查**，不得忽略後強行往下走。
- **CI 通過不代表人工 UAT 通過**；**Ruff 綠燈不代表可自動取得 Merge 授權**。
- **本機 `uv run pytest`／`ruff check` 通過不代表 GitHub CI Success**（環境、鎖定依賴、觸發條件可能不同）。
- GitHub CI、人工 Code Review、財務 UAT **不可互相替代**。
- 未實際跑過的遠端 CI：工程驗收層標 **`PENDING`**（Reason 可註原用語 `NOT_RUN`）；不得標 `PASS`。

### 2.7 Code Review

由 Cursor Agent 以**獨立 Reviewer** 角度檢查（與實作 Agent 角色分離）：

- 程式邏輯
- 安全性（機密、路徑、資料外洩、權限）
- 財務計算（FIFO、TRUNC、費用、守恆）
- 測試覆蓋與邊界條件
- 規格與實作一致性
- 是否破壞既有功能／契約
- 工程四態與 Pending 登記是否被規避（見 Integrity）

輸出結論之一：

- `PASS`
- `PASS WITH NOTES`
- `FAIL`

每個問題應提供：**嚴重程度、檔案、行號、原因、建議**（建議含 Finding ID、Evidence、Violated Rule、Verification Method）。

- Code Review **不得**自行修改程式或 Merge，除非另有明確授權。
- Review 通過不取代 UAT。
- 實作 Agent **不得**以自我檢查冒充 Independent CR。

### 2.8 UAT（使用者驗收）

由**使用者**進行業務驗收。自動化 pytest 全綠**不能**取代 UAT。

對財務功能，至少確認：

1. 原始交易與正規化資料一致
2. FIFO 股數與配對正確
3. 買進成本、賣出收入及已實現損益正確
4. TRUNC 與尾差規則符合 SPEC
5. 手續費、交易稅與利息歸屬正確
6. 原始交易與拆分片段金額守恆
7. 未配對交易與例外完整記錄
8. 正式資料庫、原始檔與歷史證據**未被覆寫**

UAT 必須使用可追溯的資料與證據（隔離 DB／時間戳輸出／audit／exceptions），並可寫入 `TDD_STATUS.md` 或專案 RCA／驗收紀錄。

**UAT 產出路徑與隔離（強制慣例）**：

| 類型 | 路徑 | 說明 |
|---|---|---|
| Excel／稽核／例外／配對與守恆報表 | `output/uat_<主題>/` | **統一**寫入；含明細 xlsx、audit json、exceptions csv、FIFO 配對／未配對明細、價金費用守恆表等；勿寫到 `data/uat/**/results` 或其他散落目錄 |
| SQLite 測試副本／Backup 快照 | `data/uat/<主題>/` 或既有規範之 `data/uat_<主題>.db` | 僅隔離資料庫；**不**放 Excel／報表 |
| 正式 DB／正式報表 | `data/trading.db`、非 UAT 的 `output/` 子目錄 | **禁止**對正式資料庫執行 UAT 寫入（含 match／report／migrate／VACUUM）；不得覆寫歷史 UAT 時間戳檔 |

**每次 UAT 最低產出（人工可檢查）**：

1. FIFO 配對明細（含未配對）
2. 剩餘庫存可追溯資訊
3. 成本／收入／已實現損益（或同等稽核欄）
4. 數量守恆結果（`conservation_ok`／守恆表）
5. 例外清單（含 blocking 與非 blocking）

有 **blocking** 例外時，明細報表檔名必須標示 **DRAFT**（使用 `--allow-partial`）；不得以正式檔名冒充已清帳。無 blocking 才可產正式（非 DRAFT）明細。

`output/` 與 `data/` 已由 `.gitignore` 排除，真實 UAT 明細與 DB 副本不上傳 Git。CLI 範例：`report detail --allow-partial --output-dir output/uat_<主題> --db <隔離副本>`（`--db` 置於子命令參數之後）。

UAT **個別檢查項目**之工程驗收結果使用四態（`PASS`／`FAIL`／`PENDING`／`N/A`）；產品既有 UAT／Golden **整體裁決語意**保留，**不得**另建工程 Overall PASS 聚合器，也不得以合成測試冒充真實資料 UAT。

### 2.9 Merge

只有同時符合以下條件，才可合併：

1. 規格符合需求（PRD／SPEC）
2. TDD 與本機 REGRESSION 通過
3. GitHub CI Success
4. Code Review 無未解決的阻擋問題（`FAIL` 或未解決阻擋項）
5. UAT 通過（適用時；文件／純基礎設施變更可依風險豁免，但仍須使用者確認）
6. **使用者明確授權 Merge**

合併後核對：

- GitHub PR 狀態
- Merge Commit
- 本機／遠端 `master` 同步
- master 上 CI 結果

**不得**因 PR 顯示 CLEAN／Checks 綠燈就自行 Merge。

### 2.9.1 Owner 決策：Regression 門檻與正式驗收順序（方案 A）

**Owner 選擇方案 A（Stage E.2）**：保留既有本機 Regression 合併門檻；**本輪不採用**「文件-only Regression 豁免」。
**不得**降低既有必要驗收門檻。**不得**要求日常單元測試一律重新建立 Clone。

正式 Regression／Ruff／完整 Pytest **不應**直接在持有正式交易資料的工作目錄執行；應於獨立驗收環境進行（見 §2.10）。

建議工作順序（後續執行指引；**不**表示當下已取得 Runtime／Commit／Push 授權）：

1. Findings 文件修正（本輪）
2. 局部 Independent CR
3. Owner 授權 Commit，確立待驗收版本
4. 建立獨立驗收環境
5. Lockfile 一致性驗證
6. Ruff／完整 Pytest（含必要 Regression 核對；分層證據見 §4／`VP-TR-004`）
7. Push／PR／遠端 CI
8. Owner 授權 Merge

Stage F 中獨立環境、Lockfile、Ruff、Pytest 可依上述順序提前執行。
**Migration 副本**及**正式資料庫升級**仍為**另外授權**事項（見 `VP-TR-005`／`VP-TR-006`）；不得因本輪未執行 Runtime 而將其標為 `N/A`。

### 2.10 風險導向獨立驗收環境（Isolated Verification）

依**風險**選擇隔離程度；**不**預設一律 Worktree／Clean Clone。
產品 UAT 路徑細節見 §2.8；測資分層見 §2.2.1；備份／產物分類見 [`BACKUP_AND_ARTIFACT_POLICY.md`](BACKUP_AND_ARTIFACT_POLICY.md)。

| 情境 | 隔離選擇 |
|---|---|
| 日常 TDD | **不強制**每次建立獨立 Clone；可用工作區＋合成／公開 fixture／`tmp_path` |
| CI（公開） | 遠端 Job 僅合成／公開安全資料；**不代表**本機已完成安全隔離 |
| 平行開發 | Git Worktree 可用（仍 ≠ OS 沙箱） |
| 正式版本驗收／正式 Regression（含持久化／敏感） | **優先 Clean Clone** 或其他適當隔離環境；**避免**在含正式交易資料之工作目錄直接執行 |
| 經授權私人資料驗收 | 隔離環境＋Private Fixture Gate＋§2.8 路徑；最小必要資料；不上傳公開 Git／CI |
| 真實資料人工 UAT | 僅用**經授權**之必要測資＋隔離產出／資料路徑（§2.8）；**不得**直接操作正式資料 |
| Database Migration 驗收 | 使用**獨立資料庫**、可重建測試庫，或**經核准**的 DB 副本；**禁止**未授權對正式 DB 執行 Migration；另案授權 |
| 高風險（破壞性、權限擴大、不可逆） | 評估 Container／VM／權限隔離 |

共通強制：

- Worktree／Clean Clone **≠** OS 安全沙箱。
- **禁止**未授權讀寫正式／敏感生產資料庫或正式資料路徑；**禁止**未授權對正式 DB 執行 Migration。
- `git diff` 空僅證明所涵蓋 Git 路徑未異動，**不代表**正式 DB 或私人備份內容完整性已驗證。
- 驗收前檢查：外部路徑、環境變數、私人測資位置、獨立 venv、DB／產出路徑是否指向隔離位置。
- 缺環境或權限時，相關驗收項標 **`PENDING`**，登記於 [`test/PENDING_DATA_VALIDATION.md`](test/PENDING_DATA_VALIDATION.md)；不停止其他已具備條件的工作。

---

## 3. Agent 權限邊界（強制）

| 動作 | 預設 | 例外 |
|---|---|---|
| 讀取規格／程式／測試結果 | 允許 | — |
| 修改業務程式／測試 | 僅在任務授權範圍內 | 財務契約不得擅自放寬 |
| 本機 `git commit` | **禁止** | 使用者明確要求「請 commit」等 |
| 一般 `git push`（非 force） | **禁止** | 使用者明確要求 Push（仍不得擴張為 Force Push／PR／Merge） |
| Force Push／改寫遠端歷史 | **禁止** | **無例外**（僅使用者親自評估與操作；Agent 永不執行） |
| 建立／合併 PR | **禁止** | 使用者明確要求 |
| 取得／使用個人 GitHub Token 或擴大 repo 寫入權限 | **禁止** | 無例外（由使用者自行操作） |
| 修改 `.github/workflows/*` | 僅在任務明確要求時 | 不得順便「加強」未要求的 CI 行為 |
| 讀寫正式 DB／真實對帳單／覆寫歷史 UAT 輸出 | **禁止** | 使用者明確的本機手動驗收指示 |
| 啟動 DEFERRED／強制新增 NOT_ADOPTED 工具 | **禁止** | Owner 明確授權 |
| 自行建立 Git Tag／冒充 Independent CR | **禁止** | Owner 明確授權（CR 另指派） |

---

## 4. 「通過」的定義（防混淆；分層）

| 名稱 | 意義 | 不代表 |
|---|---|---|
| **工具執行成功** | 已採用工具（如 `ruff check`、`pytest`）有真實執行證據且該次 **Exit Code** 符合該工具成功語意 | 不代表所有測試案例通過；不代表需求驗收；不代表真實資料業務驗收；不是 Overall 聚合 |
| **個別測試案例通過** | 單一 test node 已執行且斷言／契約成立（原生 Passed；非 skip 冒充） | 不代表同需求其他案例；不代表真實資料驗收 |
| **需求驗收通過** | 對應 PRD／SPEC／Pending 需求之必要證據齊備且通過（獨立預期結果） | 不因工具 exit 0、CI 綠燈或「跑了很多測試」自動成立 |
| **真實資料業務驗收通過** | 經授權私人測資／Golden／人工 UAT 等，且符合 Gate／隔離／獨立預期 | 合成測試通過 ≠ 本項完成 |
| **GitHub CI Success** | Actions 依 `pytest.yml` 在 PR／master 上 **lint 與 pytest Job 皆依 YAML 成功** | 不代表人工 UAT；不代表可自動 Merge；不代表所有需求驗收完成 |
| **人工 UAT 通過** | 使用者依業務清單驗收並留下可追溯證據 | 不因 pytest／CI 全綠而自動成立 |

Pytest／Regression 證據強制：

- 記錄適用之 **Passed、Failed、Skipped、XFailed、XPassed**（或同等摘要）與 **Exit Code**；Skipped／XFailed 須附**原因**。
- Exit Code `0` **不代表**所有測試案例及需求均已通過。
- 缺私人測資而跳過的測試 → 對應需求維持 **`PENDING`**。
- 已執行且符合明確條件 → 可標 **`PASS`**；已證實不符合 → 標 **`FAIL`**。
- **禁止**新建工程 Overall PASS 聚合器。詳見 `VP-TR-004`。

---

## 5. 建議的最小作業檢查表

開發／修復一個變更時：

1. [ ] 已讀相關 PRD／SPEC／TDD／Integrity／Pending（若相關）
2. [ ] RED 有真實失敗證據（若屬新需求／Bug）
3. [ ] GREEN 最小實作；財務斷言未放寬；測資分層符合 §2.2.1
4. [ ] REFACTOR（若有）後行為不變
5. [ ] 已採用工具分層記錄（Ruff／Pytest：Exit Code＋原生計數）；`TDD_STATUS.md` 已更新；skip→需求 PENDING
6. [ ] 無法完成的驗證已寫入 `docs/test/PENDING_DATA_VALIDATION.md`（不得虛構 PASS）
7. [ ] 正式 Regression 不在含正式交易資料之工作目錄執行（見 §2.9.1／§2.10）
8. [ ] Commit 僅含授權範圍；無正式資料／機密／私人測資
9. [ ] 使用者 Push → 開 PR（含 Summary／測試／風險／待驗收）
10. [ ] GitHub CI Success；失敗已調查
11. [ ] Code Review：`PASS`／`PASS WITH NOTES`／`FAIL`（Independent；非實作自檢）
12. [ ] UAT／私人驗收（適用時）通過且證據可追溯；隔離路徑符合 §2.8／§2.10
13. [ ] 使用者授權後才 Merge；合併後核對 master／CI

---

## 6. 與既有規範的關係

- **不覆寫** PRD／SPEC 財務與欄位規格；流程文件只引用。
- **不重複** 在多份 `.mdc` 展開完整流程；詳細步驟集中於本檔。
- Python 風格以 [`docs/CODING_STANDARDS.md`](CODING_STANDARDS.md) 為準；本檔不另寫第二套風格指南。
- `TDD.md` 維持測試方法主文件；本檔引用其階段，不另寫第二套 TDD。
- `TDD_STATUS.md` 只記錄實際執行；計畫中的測試不得寫成已通過。
- 工程驗收狀態模型以 [`AGENT_INTEGRITY.md`](AGENT_INTEGRITY.md) 為準；待驗證清單以 [`test/PENDING_DATA_VALIDATION.md`](test/PENDING_DATA_VALIDATION.md) 為準（**不**另建母版同名 `VERIFICATION_PENDING.md`）。
- 規範版本與工具採用以 [`STANDARDS_VERSION.md`](../STANDARDS_VERSION.md) 為準。
- GitHub Workflow 行為以 YAML 為準；本檔表格若與 YAML 不一致，**以 YAML 為準**並應修正本檔。

---

## 7. 已知既有衝突

| 項目 | 現況 | 狀態／建議 |
|---|---|---|
| Python 版本敘述 | 基準為 `.python-version`＝`3.11`、`requires-python = ">=3.11"`、CI `python-version: "3.11"` | **已修正**：`py-env.mdc` 由誤寫 3.13 改為 3.11 |
| `backend-rule.mdc` | 曾含 LLM／embedding 範本與 `cd backend` | **已修訂**（見 [`docs/audit/CODING_STANDARDS_ALIGNMENT.md`](audit/CODING_STANDARDS_ALIGNMENT.md)）：根目錄 uv；依賴以 `pyproject.toml` 為唯一權威；強制引用 `docs/CODING_STANDARDS.md` |
| Python 風格權威 | 曾缺集中文件 | **已新增** `docs/CODING_STANDARDS.md`；稽核見 `docs/audit/CODING_STANDARDS_ALIGNMENT.md` |
| Ruff／CI | Phase D：`pyproject` 已凍結 0.17.6 等效 `lint.select`；CI 並列 lint＋pytest | **已實施**（詳見 `CODING_STANDARDS` §7、`TDD_STATUS` Phase D）；Format／D 規則仍另案 |
| TDD 階段命名 | 口語常說 RED→GREEN→REGRESSION；`TDD.md` 含 REFACTOR | 以 `TDD.md` 四階段為準；本流程已對齊 |

其餘未決衝突**不阻斷**本流程文件生效；工具節奏決策見 Coding Standards 稽核報告。

---

## 8. 文件維護慣例（最小約束）

目的：避免第二套 Markdown／風格權威，並降低 Agent 誤讀歷史證據。

1. **權威不雙重維護**：流程→本檔；誠信／四態→`AGENT_INTEGRITY`；待驗證→`PENDING_DATA_VALIDATION`；風格→`CODING_STANDARDS`；TDD 方法→`TDD.md`；業務→PRD；技術／財務契約→SPEC；依賴→`pyproject.toml`；CI→`.github/workflows/pytest.yml`；版本→`STANDARDS_VERSION`。Rules 只做精簡指針（入口見 `AGENTS.md`）。
2. **相對連結**：自檔案位置計算；新增連結前確認 Git 已追蹤目標。
3. **現行 vs 歷史**：Class A／B（權威／操作）可最小修正過時指令；Class C（TDD_STATUS／RCA／UAT／audit）**保留史實**，僅追加具日期與基準 Commit 的後補說明。歷史 FAIL／PENDING_DATA **不得**抹除或降級。
4. **命令列區塊**：優先標 `powershell`（Windows）；並註明於專案**根目錄**執行。
5. **最小修改**：一次只修誤導、斷鏈與明確錯誤；不做全庫美化，不與 Python 重構混在同一 PR。
6. **證據索引**：見 README「證據與歷史文件索引」；RCA／UAT 檔頂應標明歷史快照性質。
