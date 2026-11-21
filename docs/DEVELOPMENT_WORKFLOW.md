# trading_report — 品質開發流程（主文件）

本文件是本專案 **端到端品質開發流程** 的唯一正式來源。
財務規格、欄位契約與測試方法仍分別以 PRD／SPEC／TDD 為準；本檔只定義「如何把變更安全地送到 master」。

| 文件 | 職責 |
|---|---|
| `docs/DEVELOPMENT_WORKFLOW.md`（本檔） | PRD→TDD→Commit→Push→PR→CI→Review→UAT→Merge 全流程 |
| `docs/prd/PRD.md` | 產品需求、業務規則、驗收案例 |
| `docs/spec/SPEC.md` | 技術規格、schema、FIFO／費用／報表契約、驗證矩陣 |
| `docs/test/TDD.md` | TDD 方法（RED→GREEN→REFACTOR→REGRESSION） |
| `docs/test/TDD_STATUS.md` | **實際**測試結果與 Commit／稽核證據（不得寫計畫中的通過） |
| `.github/workflows/pytest.yml` | GitHub Actions pytest CI 的實際設定 |
| `.cursor/rules/dev-workflow-rule.mdc` | 強制 Agent 遵守本流程的精簡規則 |
| `.cursor/rules/tdd-rule.mdc` | 強制 Agent 遵守 `TDD.md` |
| `.cursor/rules/commit-rule.mdc` | Commit message 格式 |

Agent 與開發者不得另建平行「流程指南」重複維護相同內容。若本檔與 Cursor Rule 衝突，以本檔為準並回報不一致處。

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

- 保留真實測試輸出與必要證據（見 `TDD_STATUS.md`）。
- **不得**只為了通過測試而放寬財務斷言。
- **不得**使用真實交易資料、正式 DB、正式報表做自動化測試。
- 既有「先實作後補測」屬特徵化／回歸，不得偽稱為當次 TDD 完成。

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
| 環境 | `ubuntu-latest`；Python **3.11**；`astral-sh/setup-uv`（pin commit） |
| 依賴 | `uv sync --locked --dev` |
| 測試 | `uv run --locked pytest -q` |
| Checkout | `persist-credentials: false`（避免步驟內遠端寫入） |

硬性規則：

- **不**使用個人 PAT 或不必要的 Secrets 跑此 pytest workflow。
- CI **不得**自動 Push、修改正式資料或 Merge。
- CI Failure **必須先調查**，不得忽略後強行往下走。
- **CI 通過不代表人工 UAT 通過**。
- **本機 `uv run pytest` 通過不代表 GitHub CI Success**（環境、鎖定依賴、觸發條件可能不同）。

### 2.7 Code Review

由 Cursor Agent 以**獨立 Reviewer** 角度檢查（與實作 Agent 角色分離）：

- 程式邏輯
- 安全性（機密、路徑、資料外洩、權限）
- 財務計算（FIFO、TRUNC、費用、守恆）
- 測試覆蓋與邊界條件
- 規格與實作一致性
- 是否破壞既有功能／契約

輸出結論之一：

- `PASS`
- `PASS WITH NOTES`
- `FAIL`

每個問題應提供：**嚴重程度、檔案、行號、原因、建議**。

- Code Review **不得**自行修改程式或 Merge，除非另有明確授權。
- Review 通過不取代 UAT。

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

---

## 4. 三種「通過」的定義（防混淆）

| 名稱 | 意義 | 不代表 |
|---|---|---|
| **本機 pytest / REGRESSION** | 開發者機器上 `uv run pytest`（或指定子集）通過 | 不代表 GitHub CI；不代表財務 UAT |
| **GitHub CI Success** | Actions 依 `pytest.yml` 在 PR／master 上通過 | 不代表人工 UAT；不代表可自動 Merge |
| **人工 UAT 通過** | 使用者依業務清單驗收並留下可追溯證據 | 不因 pytest／CI 全綠而自動成立 |

---

## 5. 建議的最小作業檢查表

開發／修復一個變更時：

1. [ ] 已讀相關 PRD／SPEC／既有測試
2. [ ] RED 有真實失敗證據（若屬新需求／Bug）
3. [ ] GREEN 最小實作；財務斷言未放寬
4. [ ] REFACTOR（若有）後行為不變
5. [ ] 全量 `uv run pytest -q` 通過；`TDD_STATUS.md` 已更新真實結果
6. [ ] Commit 僅含授權範圍；無正式資料／機密
7. [ ] 使用者 Push → 開 PR（含 Summary／測試／風險／待驗收）
8. [ ] GitHub CI Success；失敗已調查
9. [ ] Code Review：`PASS`／`PASS WITH NOTES`／`FAIL`
10. [ ] UAT（適用時）通過且證據可追溯
11. [ ] 使用者授權後才 Merge；合併後核對 master／CI

---

## 6. 與既有規範的關係

- **不覆寫** PRD／SPEC 財務與欄位規格；流程文件只引用。
- **不重複** 在多份 `.mdc` 展開完整流程；詳細步驟集中於本檔。
- `TDD.md` 維持測試方法主文件；本檔引用其階段，不另寫第二套 TDD。
- `TDD_STATUS.md` 只記錄實際執行；計畫中的測試不得寫成已通過。
- GitHub Workflow 行為以 YAML 為準；本檔表格若與 YAML 不一致，**以 YAML 為準**並應修正本檔。

---

## 7. 已知既有衝突

| 項目 | 現況 | 狀態／建議 |
|---|---|---|
| Python 版本敘述 | 基準為 `.python-version`＝`3.11`、`requires-python = ">=3.11"`、CI `python-version: "3.11"` | **已於本分支修正**：`py-env.mdc` 由誤寫 3.13 改為 3.11 |
| `backend-rule.mdc` 依賴示例 | 含 LLM／embedding 等與本專案無關的示例 | 後續改為本專案實際依賴（SQLAlchemy、openpyxl 等）或標明「範本遺留」 |
| TDD 階段命名 | 口語常說 RED→GREEN→REGRESSION；`TDD.md` 含 REFACTOR | 以 `TDD.md` 四階段為準；本流程已對齊 |

其餘未決衝突**不阻斷**本流程文件生效；修正屬獨立文件整理任務。
