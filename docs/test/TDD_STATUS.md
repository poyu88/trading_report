# TDD 測試狀態與稽核紀錄

> **文件性質**：本檔為**歷史／現行測試證據**（Class C）。勿當操作手冊或第二套 SPEC。契約以 PRD／SPEC 為準；TDD 方法以 `docs/test/TDD.md` 為準。

依 `docs/test/TDD.md`、`docs/spec/SPEC.md` §12、以及本檔生命週期追蹤表維護。

> **稽核結論（2026-11-21）**：既有 **34** 項屬**特徵化／回歸安全網**（基準 `cf4e68e`）。`esun_xlsx_v1`、`day_trade_v1`、Cloud Agent **`esun_unsupported_rows_v1`**，以及本機整合後的補充覆蓋，均見 §6.2。
>
> **回歸基準 Commit**：`cf4e68e`。分支基準：`c537d8b`。
>
> **後補（2026-11-22；不覆寫上方歷史列）**：PR #6（品質流程）、PR #7（CASH 庫存優先 FIFO／CR 修正）、PR #8（Coding Standards）**已**合入 `master`（當時 tip 參考 `58430d5`）。全量通過數以本檔最新 §1.x REGRESSION 為準（PR #7 後曾記錄 **120 passed**）。

---

## 1. 實際執行狀態（非文件自述）

### 1.1 回歸基準（歷史）

| 項目 | 結果 |
|---|---|
| 指令 | `uv run pytest -v --tb=line` |
| 收集數 | 34 |
| 結果 | **34 passed** |
| 日期 | 2026-11-20 |

### 1.2 玉山解析完成後（歷史 REGRESSION）

| 項目 | 結果 |
|---|---|
| 指令 | `uv run pytest -q --tb=line` |
| 收集數 | 43（原 34 + 玉山新增 9） |
| 結果 | **43 passed** |
| 日期 | 2026-11-20 |

### 1.3 現沖 DAY_TRADE 支援後（歷史 REGRESSION）

| 項目 | 結果 |
|---|---|
| 指令 | `uv run pytest -q --tb=line` |
| 收集數 | 52 |
| 結果 | **52 passed**（0 failed / 0 skipped） |
| 耗時 | 約 61s（2026-11-20） |
| 正式 DB | `data/trading.db` mtime 仍為 2026-11-20 18:51:21；**未** apply／migrate |
| 真實 Preview | `trade_count=65`、`error_count=0`、buy 23／sell 42；`source_reconciliation.matched=true`（價金 1800949／費 2533／稅 2765）；來源 SHA／mtime 不變 |

### 1.4 玉山未支援列例外後（Cloud Agent 歷史 REGRESSION）

| 項目 | 結果 |
|---|---|
| 指令 | `uv run pytest -q --tb=line` |
| 收集數 | 53（原 52 + 1） |
| 結果 | **53 passed**（0 failed / 0 skipped） |
| 耗時 | 約 28s（2026-11-20） |
| 修復 | Bugbot／Cloud Agent：融資等未支援交易類別不得靜默丟棄 → `UNSUPPORTED_TRADE_TYPE` |
| Commits | RED `fb8d5f2` → GREEN `a0df837` → doc `592e1a5`（分支 `cursor/fix-esun-unsupported-rows-d1e5`） |

### 1.5 本機整合補充覆蓋後（歷史 REGRESSION）

| 項目 | 結果 |
|---|---|
| 指令 | `uv run pytest -q --tb=line` |
| 收集數 | 55（53 + 本機補充 2） |
| 結果 | **55 passed**（0 failed / 0 skipped） |
| 耗時 | 約 74s（2026-11-21） |
| 正式 DB | **未** apply／migrate |
| 整合 | Fast-forward 合併 Cloud PR #2；保留其 RED／GREEN／doc；另補融資＋配股 preview、apply→`raw_rows`、來源核對區分；**非** Cloud 原始 RED 回填 |
| 補充 commit | `7a3a2f8`（測試）；整合 doc `6c231a2` |

### 1.6 合併前文件對齊後（歷史 REGRESSION）

| 項目 | 結果 |
|---|---|
| 指令 | `uv run pytest -q --tb=line` |
| 收集數 | 55 |
| 結果 | **55 passed**（0 failed / 0 skipped） |
| 耗時 | 約 68s（2026-11-21） |
| 正式 DB | mtime 仍為 2026-11-20 18:51:21；**未** apply／migrate |
| 文件 | 對齊 PRD §2.3／SPEC §4.2.1／ING-08／README：候選列／已正規化／未支援／來源核對；**未改** parser 業務規則 |
| TDD 證據 | Cloud RED／GREEN（`fb8d5f2`／`a0df837`）與本機補充（`7a3a2f8`）歷史**未改寫** |

### 1.7 玉山 FIFO 財務／未配對投影修正後（歷史 REGRESSION）

| 項目 | 結果 |
|---|---|
| 指令 | `uv run pytest -q --tb=line` |
| 收集數 | 77（原 55 + UAT 財務守恆 22） |
| 結果 | **77 passed**（0 failed / 0 skipped） |
| 耗時 | 約 57s（2026-11-21） |
| 正式 DB | **未** apply／migrate／覆寫 |
| 舊 UAT 輸出 | **未**覆寫 `output/uat_esun/交易明細_DRAFT_2026-11-21_00-58-47*` |
| 根因 | 見 `docs/test/RCA_esun_fifo_finance.md`（高估 151146.60 於 `detail_projector` 賣出價金拆分） |
| Commits | 規格 `03a2918` → RED `65f4459`（10 failed／12 passed）→ GREEN `71e21a7`；共用計算於 GREEN 抽出 `report_finance`（無獨立 restruct commit） |

### 1.8 片段價金 TRUNC＋±1 容許差（歷史 REGRESSION）

| 項目 | 結果 |
|---|---|
| 指令 | `uv run pytest -q`（收斂前重跑） |
| 收集數 | 90（原 77 + `test_fragment_gross_trunc` 13） |
| 結果 | **90 passed**（0 failed / 0 skipped） |
| 耗時 | 68.02s（2026-11-21） |
| 正式 DB | mtime 仍為 2026-11-20 18:51:21；**未** apply／migrate／覆寫 |
| 舊 UAT 輸出 | **未**覆寫 `output/uat_esun/交易明細_DRAFT_2026-11-21_00-58-47*`／`09-12-41*` |
| 隔離 E2E | DB `data/uat_esun_trunc_20261121.db`；輸出 `output/uat_esun_trunc/交易明細_DRAFT_2026-11-21_09-59-30*`；守恆 **65/65** ok、超限 **0**；相對 `09-12-41` 差異 35 格 |
| 人工 UAT | **已通過**（2026-11-21） |
| Commit | `fix: apply TRUNC fragment pricing with bounded residual reconciliation`（本提交；保留既有 4 筆 FIFO 修正 commits，不 squash／amend） |

### 1.9 群益 HTML 財務合成回歸（歷史 REGRESSION）

| 項目 | 結果 |
|---|---|
| 指令 | `uv run pytest tests/test_capital_html_finance_regression.py -v`；全量 `uv run pytest -q` |
| 收集數 | 94（原 90 + 群益 HTML 財務回歸 4） |
| 結果 | **94 passed**（0 failed / 0 skipped） |
| 耗時 | 新測約 1.18s；全量 57.15s（2026-11-21） |
| 正式 DB | **未** apply／migrate／覆寫 |
| 真實對帳單／舊 DRAFT | **未**讀寫／覆寫；隔離 UAT 見 `data/uat_capital.db`、`output/uat_capital/`（gitignore） |
| RCA | `docs/test/RCA_capital_fifo_finance.md`：現況無必修 Bug；HIST-01 僅歷史舊 DRAFT |
| 判定 | **特徵化／回歸**（行為已存在於共用財務層；**非**虛構 RED） |

### 1.10 GitHub Actions pytest CI（歷史 REGRESSION → 已合併）

| 項目 | 結果 |
|---|---|
| 分支 | `feature/github-actions-pytest` |
| 變更 | 新增 `.github/workflows/pytest.yml`（push／PR → `master`；`contents: read`；Python 3.11 + uv + `uv.lock`） |
| 指令 | `uv sync --locked --dev`；`uv run --locked pytest -q --tb=line` |
| 收集數 | 94 |
| 結果 | **94 passed**（0 failed / 0 skipped） |
| 耗時 | 65.52s（2026-11-21） |
| 正式 DB／真實對帳單／UAT Excel／財務報表 | **未**讀寫／上傳／覆寫 |
| 業務碼 | **未**改 FIFO／財務邏輯；**無** skip／放寬財務斷言 |
| CI 安全稽核 | 見 §9；測試僅合成 fixture／`tmp_path`；路徑以 `pathlib`；fixture 檔名全小寫 |
| 合併 | PR **#5** 已合併至 `master`（Merge `92f5ab3`）；CI 已在 PR 與 master Push 成功執行（以 GitHub Actions 為準） |
| 判定 | **基礎設施／回歸驗證**（非業務 RED→GREEN） |

### 1.11 品質開發流程文件整合（本任務；僅文件／規範）

| 項目 | 結果 |
|---|---|
| 分支 | `docs/quality-development-workflow`（自同步 `master`＠`92f5ab3` 建立） |
| 變更範圍 | 新增 `docs/DEVELOPMENT_WORKFLOW.md`、`.cursor/rules/dev-workflow-rule.mdc`；增量更新 PRD／SPEC／TDD／README／本檔／`commit-rule.mdc`；`py-env.mdc` 3.13→**3.11**（對齊 `.python-version`／`pyproject.toml`／CI） |
| 業務碼／FIFO／Parser／DB／Workflow YAML | **未**修改 |
| 本機 REGRESSION | `uv run pytest -q` → **94 passed**／60.03s（2026-11-21）；`git diff --check` 通過；相對連結抽查 OK |
| Commit | `461fd37` — `docs: establish quality development workflow and agent rules`（已完成）；`2176c42` — `doc：修正 PR #6 品質流程審查意見`（已完成） |
| Push | **已** Push 至 `origin/docs/quality-development-workflow` |
| Pull Request | **已**建立 [PR #6](https://github.com/poyu88/trading_report/pull/6)（目標 `master`） |
| GitHub CI | **Success**（Python CI／Actions run #4，約 38s；以 GitHub Actions 為準） |
| Code Review | **PASS WITH NOTES**（獨立 Review；未授權改碼或 Merge） |
| Merge | **已**合併至 `master`（Merge `15d7837`） |
| 判定 | **文件／規範**；非業務 TDD；本機 pytest ≠ GitHub CI ≠ 財務 UAT |

### 1.12 CASH 開盤前庫存優先 FIFO（本任務）

| 項目 | 結果 |
|---|---|
| 分支 | `feat/cash-prior-inventory-fifo`（自同步 `master`＠`15d7837` 建立） |
| 變更 | `fifo_matcher`：CASH 按日先賣後入庫買；`detect_order_ambiguity` 對現行輸入回傳空；改寫／新增 `test_fifo` Case1–10＋1589；SPEC／PRD／README／本檔 |
| RED | `uv run pytest tests/test_fifo.py -q` → **12 failed / 5 passed**（主因 `ORDER_AMBIGUITY` 短路整組，或依 time 用當日 BUY 解套） |
| GREEN | `_run_cash_group` 按日先 SELL 後 BUY；DAY_TRADE 不動；目標測全綠 |
| REFACTOR | GREEN 已抽出 `_cash_day_sort_key`；無獨立 restruct commit |
| 本機 REGRESSION | `uv run pytest -q` → **106 passed**／76.53s（2026-11-22）；`git diff --check` 通過；正式 DB **未**動 |
| 判定 | **有證據 TDD**（見 §6.2 `cash_prior_inventory_fifo_v1`） |

### 1.13 PR #7 CR-01～04 修正與副本 UAT（本任務）

| 項目 | 結果 |
|---|---|
| 分支 | `feat/cash-prior-inventory-fifo`（自 `77f3ed7` 續作） |
| 變更 | `ALGORITHM_VERSION`→`fifo_v2_cash_prior_inventory`；`quantity_conservation`／`build_audit` 納入 approved opening；`input_fingerprint` 含 source_order／帳戶／幣別／政策；Backup 預設 ro；合成 SQLite 整合測；PRD／SPEC／UAT 摘要 |
| RED | `uv run pytest tests/test_fifo_cr_fixes.py tests/test_fifo_sqlite_integration.py -q` → **9 failed／5 passed**（版本仍 `fifo_v1`、守恆拒 `opening_lots`、fingerprint 未含 source_order） |
| GREEN | 最小改 `config`／`allocation_service`／`reconciliation`／`fifo_matcher`／`backup_service`；同檔 **14 passed** |
| REFACTOR | 無獨立結構重構（僅 import 整理） |
| 本機 REGRESSION | `uv run pytest -q` → **120 passed**／65.16s（2026-11-22）；`test_fifo` 17 passed；正式 DB **未**動 |
| 副本 UAT | 見 `docs/test/PR7_FIFO_UAT.md`；基準 worktree＠`77f3ed7` vs 候選；1589 同日賣沖 2/3 舊庫存；結論 **APPROVE** |
| 判定 | **有證據 TDD**（見 §6.2 `pr7_fifo_cr_fixes_v1`） |

### 1.14 歷史文件一致性 Phase B（本任務；僅文件／Rules）

| 項目 | 結果 |
|---|---|
| 分支 | `docs/history-standardization-phase-b`（自 `master`＠`58430d5`） |
| 變更範圍 | SPEC／PRD 狀態與欄 E／§9／CLI 敘述；README UAT 路徑；BUGBOT 指針；TDD.md 導覽；本檔後補；Workflow §7 路徑＋§8 文件慣例；Class C 橫幅；`commit-rule` 尾符號 |
| 業務碼／測試／CI YAML | **未**修改 |
| 本機 REGRESSION | `uv run pytest -q` → **120 passed**／56.69s（2026-11-22）；`git diff --check` 通過；正式 DB **未**動 |
| 判定 | **文件整理**（非業務 TDD）；正式 DB **未**動；未納入 `.cursor/plans/`、`esun_local_changes.patch`、`scripts/` |

### 1.15 Phase C Python 品質改善（本任務；REFACTOR）

| 項目 | 結果 |
|---|---|
| 基準 | `master`＠`471784d`；K 節預設：刪暫存、C1 含 alembic UP、C3 清測試 FURB157、C4 僅常數／RUF015／parser（**不做**大面積財務 format）、BLE001／PLW1510 保留、修 SIM222；**未**改 Phase D／CI |
| 變更範圍 | C1 import／UP／RUF010；C2 公開 API Google docstring＋`report_finance` Protocol；C3 測試 FURB157／F841／RUF059／SIM222；C4 `AMOUNT_TOLERANCE=Decimal(1)`、UAT RUF015、`esun_xlsx_parser` SIM103／PIE810 |
| 財務公式／FIFO 政策／報表 A～W 契約／財務 assert | **未**改寫語意；斷言**未**放寬 |
| 正式 DB／真實對帳單／正式 output | **未**讀寫 |
| Ruff（tracked） | 222 → **3**（剩餘 hooks BLE001×2、契約測 PLW1510×1，刻意保留） |
| 本機 REGRESSION | `uv run pytest -q --tb=line` → **120 passed**／69.47s（2026-11-22） |
| 判定 | **品質 REFACTOR／回歸**（非業務 RED→GREEN）；Phase D `lint.select`／窄集合 CI **另案** |
| Commit（寫入當時） | **尚未**建立（待使用者授權） |

> **後補（2026-11-22；不覆寫上方「寫入當時」列）**  
> - Commit：`ad80c06` — `restruct：Phase C 品質整理與公開 API docstring`  
> - Push／PR：[PR #10](https://github.com/poyu88/trading_report/pull/10)（`feature/phase-c-python-quality` → `master`）  
> - GitHub CI：Actions run [`45035063117`](https://github.com/poyu88/trading_report/actions/runs/45035063117) → **SUCCESS**（僅 pytest；≠ 本機 pytest 替代）  
> - 獨立 CR：**PASS WITH NOTES**；Finding 1（`Sequence[Protocol]`）／Finding 2（本後補）於後續 commit 補正；Finding 3／4 另案追蹤  
> - CR Finding 1／2 補正後本機 REGRESSION：`uv run pytest -q --tb=line` → **120 passed**／68.91s（2026-11-22）；財務迴圈未改  

### 1.16 Phase D Ruff 規則標準化與 CI 整合（本任務；品質基礎設施）

| 項目 | 結果 |
|---|---|
| 基準 | `master`＠`f05a415`（PR #10 已合併）；分支 `chore/phase-d-ruff-ci` |
| 變更範圍 | `pyproject.toml` 凍結 Ruff 0.17.6 等效 `lint.select`（407 codes）；Hooks BLE001 精確 noqa×2；CLI 契約測 `subprocess.run(..., check=False)`；`.github/workflows/pytest.yml` 新增獨立 `lint` Job；同步 CODING_STANDARDS／DEVELOPMENT_WORKFLOW／本檔；audit 僅後補 |
| 財務公式／FIFO／Schema／Parser／報表 A～W／財務 assert | **未**改寫 |
| 正式 DB／真實對帳單／正式 output | **未**讀寫 |
| 依賴升級 | **無**（ruff 維持 0.17.6／`uv.lock` 未改） |
| Ruff Baseline（修改前） | tracked 61 `.py`；診斷 **3**（BLE001×2、PLW1510×1）；format `--check`：**25** would reformat（僅記錄） |
| Ruff（修改後本機） | `uv run --no-sync ruff check --no-cache .` → **All checks passed**（修復 PLW1510×1；刻意豁免 BLE001×2） |
| 本機 REGRESSION | `uv run --no-sync pytest -q --tb=line` → **120 passed**／83.96s（2026-11-22） |
| GitHub CI／PR／Merge／人工 UAT／獨立 CR | 見下方後補（寫入當時為尚未） |
| 判定 | **品質基礎設施**（非業務 RED→GREEN）；Format 全庫／Google D 另案 |

> **後補（2026-11-22；本機驗證後）**
> - 本機 REGRESSION：**120 passed**／83.96s；`ruff check .` All checks passed；`git diff --check` 通過
> - Commit：`06fe96a`；Push：`origin/chore/phase-d-ruff-ci`；PR：[#11](https://github.com/poyu88/trading_report/pull/11)
>
> **後補（2026-11-22；PR #11 CI／獨立 CR；保留 FAIL 史實）**
> - GitHub CI run [`45040723414`](https://github.com/poyu88/trading_report/actions/runs/45040723414)：`pytest` **SUCCESS**；`ruff` **FAILURE**（EXE001×2：hooks 有 shebang 但非 executable；Windows 本機未觸發）
> - 獨立 CR（HEAD `06fe96a`）：**FAIL**（Blocking：EXE001 跨平台偽陰性）
> - 當時工作樹修正方向：移除兩 hooks 的 shebang（實際由 `hooks.json` 以 `uv run python …` 呼叫；不改 fail-open／敏感檢查邏輯）
>
> **後補（2026-11-22；EXE001 補正 Commit 與最新 CI／第二輪 CR）**
> - 補正 Commit：`f8b68bf` — `fix：移除 hooks shebang 以通過 CI EXE001`
> - GitHub CI run [`45041273011`](https://github.com/poyu88/trading_report/actions/runs/45041273011)：`ruff` **SUCCESS**；`pytest` **SUCCESS**（≠ 本機；≠ 覆寫 run `45040723414` 失敗史實）
> - 第二輪獨立 CR（HEAD `f8b68bf`）：**PASS WITH NOTES**（P1 RESOLVED；P2／P3 文件 NOTES）
> - Merge／人工 UAT：仍須使用者明確授權

### 1.17 Two-Pass FIFO Same-Day Reconciliation（本任務）

| 項目 | 結果 |
|---|---|
| 分支 | `feature/fifo-same-day-reconciliation`（自 `master`＠`474a95b`） |
| 變更 | CASH Pass2 同日補沖銷；`match_type`；`day_trade_annotation`；Alembic `b2c3d4e5f6a7`；SPEC／PRD／FIFO-05／FIFO-09；Case3／4／7／9／time-ignore 契約改寫 |
| RED | `uv run pytest tests/test_same_day_reconciliation.py tests/test_day_trade_annotation.py …` → **9 failed／3 passed**（缺 Pass2／`match_type`／annotation／版本仍 v2） |
| GREEN | `_run_cash_group` Pass2；`Allocation.match_type`；annotation Layer3；`ALGORITHM_VERSION=fifo_v3_two_pass_same_day_reconcile` |
| REFACTOR | 無獨立 restruct（Pass2 helper 於 GREEN 抽出） |
| 本機 REGRESSION | `uv run pytest -q` → **128 passed**／66.92s（2026-11-26）；正式 DB **未** apply／migrate／寫入 |
| RCA | `docs/test/RCA_two_pass_fifo_same_day.md` |
| 隔離 UAT | 合成 2236：`data/uat/fifo_same_day_2236/`＋`output/uat_fifo_same_day_2236/`；Pass1=3600／Pass2=400／未售0／非 DRAFT；annotation suspected=1000≠reconciled=400；正式 DB mtime 未變；見 `docs/test/UAT_fifo_same_day_2236.md` → **PASS** |
| 判定 | **有證據 TDD**（見 §6.2 `fifo_v3_two_pass_same_day_v1`）；隔離 UAT **PASS**；Commit／Push／PR／CI **待**使用者授權 |

### 1.18 PR #12 CR Fixes（本任務）

| 項目 | 結果 |
|---|---|
| 分支 | `feature/fifo-same-day-reconciliation` |
| 變更 | CR-01～13：annotation 支持股數／TWD 稅適用／AMBIGUOUS／例外隔離；migration DAY_TRADE backfill；report ON／OFF＋fault；2236 合成 E2E；UAT run 目錄保護／verdict 延後；audit 可追溯欄；Pass2 邊界回歸；docstring／SPEC |
| RED | `uv run pytest tests/test_day_trade_annotation.py -q` → **5 failed／7 passed**（缺 `half_rate_sell_qty`／AMBIGUOUS／完整 try／CR-12 欄；非 TWD 誤套 HALF_RATE） |
| GREEN | `day_trade_annotation` 契約修正；migration backfill；`include_day_trade_annotation`；UAT／E2E／matcher 邊界測 |
| REFACTOR | touched API Google docstring（無行為變更） |
| 本機 REGRESSION | `uv run pytest -q` → **145 passed**／57.98s（2026-11-26）；`uv run ruff check .` 通過；正式 DB **未** apply／migrate／寫入 |
| 判定 | **有證據 TDD**（見 §6.2 `pr12_cr_fixes_v1`）；Commit／Push／PR 回覆 **待**使用者授權 |

### 1.19 PR #12 Round-2 CR Fixes（本任務）

| 項目 | 結果 |
|---|---|
| 分支 | `feature/fifo-same-day-reconciliation` |
| 變更 | Round-2：CR-02 商品／生效日稅適用；CR-04 annotation 準備全包例外＋OFF 跳過；CR-06 原始九筆 Parser／Import E2E；CR-05 migration FK／opening／lossy downgrade；CR-07 Excel A–W 比較；CR-10／11 UAT verdict／WAL／獨立 out；CR-12 same_day vs half_rate ids |
| RED | `uv run pytest tests/test_day_trade_annotation.py tests/test_annotation_report_noninterfere.py tests/test_fifo_same_day_2236_original_import_e2e.py -q` → **7 failed／15 passed**（ETF／未知／生效日前仍 HALF；缺 CR-12 欄；prep 未隔離；缺 half_rate ids） |
| GREEN | `tw_sec_tax_v2` 分類＋生效日；report prep 邊界；原始九筆 import E2E；migration／UAT／audit 欄位強化 |
| REFACTOR | 無獨立 restruct |
| 本機 REGRESSION | `uv run pytest -q` → **153 passed**／71.67s（2026-11-26）；`uv run ruff check .` 通過；正式 DB **未** apply／migrate／寫入 |
| 判定 | **有證據 TDD**（見 §6.2 `pr12_cr_r2_v1`）；Commit／Push／PR 回覆 **待**使用者授權 |

### 1.20 PR #12 Round-3 CR Fixes（本任務）

| 項目 | 結果 |
|---|---|
| 分支 | `feature/fifo-same-day-reconciliation`（基線審查 `ddc7530`） |
| 變更 | Round-3：CR-02 `INFERRED_TW_COMMON_STOCK`＋`tw_sec_tax_v3` 有效窗；CR-06 原始序／permutation／Excel／費用守恆；CR-10 `build_uat_checks`＋反向測；CR-07 `REQUIRED_AUDIT_KEYS`＋未平倉／未配對；CR-05 migration 全財務欄；CR-11 指紋限制文件；CR-13 docstring |
| RED | 先擴充 `test_day_trade_annotation`／`test_uat_fifo_same_day_verdict`／`test_annotation_report_noninterfere`／original import E2E／migration 斷言（針對尚未滿足之 inferred／有效窗／verdict 假性通過／嚴格 audit keys） |
| GREEN | annotation v3；UAT `build_uat_checks`；非干涉嚴格化；E2E／migration／UAT 文件 |
| REFACTOR | touched API／UAT helpers Google docstring（無行為變更） |
| 本機 REGRESSION | `uv run pytest -q` → **180 passed**／64.28s（2026-11-26）；`git diff --check` 通過；`uv run ruff check .` 通過；正式 DB **未** apply／migrate／寫入 |
| 判定 | **有證據 TDD**（見 §6.2 `pr12_cr_r3_v1`）；Commit／Push／PR 回覆 **待**使用者授權 |

### 1.21 PR #12 Round-4 CR Fixes（本任務）

| 項目 | 結果 |
|---|---|
| 分支 | `feature/fifo-same-day-reconciliation`（基線審查 `07d0f31`） |
| 變更 | Round-4：CR-10A／B／C 真實 Excel 財務驗證＋檔案層故障注入；CR-06A／B／C Owner canonical 列序＋permutation 財務＋Trace 逐筆費用；CR-02A／B／C 稅期間文件／核實期限／MIXED 分類 |
| RED／證據性質 | **事後驗證／新增回歸**：本輪先寫失敗契約測並於同輪最小實作；**未**另行留存獨立 RED pytest 失敗輸出。誠實標記，不冒充已執行 RED。 |
| GREEN | `verify_detail_xlsx_finance`／`resolve_required_outputs`；`detail_xlsx_finance_ok` 必填；Owner 列序；`MIXED_INSTRUMENT_EVIDENCE`；SPEC／audit 依據欄 |
| REFACTOR | 無獨立 restruct |
| 本機 REGRESSION | `uv run pytest -q` → **205 passed**／78.18s（2026-11-26）；`uv run ruff check .` 通過；正式 DB **未** apply／migrate／寫入 |
| 判定 | **有證據（事後驗證）**（見 §6.2 `pr12_cr_r4_v1`）；Commit／Push／PR 回覆 **待**使用者授權 |

### 1.22 CR-10A 獨立財務黃金驗證（本任務）

| 項目 | 結果 |
|---|---|
| 分支 | `feature/fifo-same-day-reconciliation`（審查基線 `10eab5d`；唯一授權 **CR-10A**） |
| 變更 | `compute_finance_golden_from_uat_trades` 擴充 cost／income／interest／unsold／min_detail_rows；`verify_detail_xlsx_finance` 獨立比對 qty／fees／tax／interest／cost／income／profit＋結構下限；正向案例改多列合成；RED-07 標 skip 待辦 |
| RED | `uv run pytest tests/test_uat_fifo_same_day_verdict.py -k "cost_income_both_up or cost_income_both_down or buy_qty or sell_qty or single_row_fake or compute_finance_golden or matching_totals" -v --tb=short` → **6 failed／1 passed**（cost+1／income+1 仍 ok；qty 竄改仍 ok；單列灌總額仍 ok；golden 缺 `interest` 等鍵）。RED-06（清空必要儲存格）於舊碼已因恒等式失敗而 PASSED。 |
| GREEN | 擴充 golden；verify 獨立欄位＋`data_rows < min_detail_rows` fail-closed；多列正向 helper |
| REFACTOR | 無獨立 restruct（僅測試 import 整理） |
| 本機 REGRESSION | 相關：`tests/test_uat_fifo_same_day_verdict.py`＋`file_fault` → **43 passed／1 skipped**；全量 `uv run pytest -q` → **211 passed／1 skipped**／83.85s（2026-11-26）；`uv run ruff check scripts/uat_fifo_same_day_2236.py tests/test_uat_fifo_same_day_verdict.py` 通過；正式 DB mtime **2026-11-22**（本輪**未**寫入） |
| 判定 | **有證據 TDD**（見 §6.2 `cr10a_finance_verify_v1`）；**待複審**；Commit／Push／PR **未**執行 |

### 1.23 GOLD-CR 第二批最小修正（本任務）

| 項目 | 結果 |
|---|---|
| 分支 | `feature/fifo-same-day-reconciliation`（基線 `ba27f30`；僅授權三項） |
| 變更 | `_norm_num_key` 可序列化唯一非法鍵；`compare_fingerprint_bundles` 納入 WAL／SHM；`git_security_audit` 實際 `git ls-files` |
| RED | `uv run pytest tests/test_golden_cr_fixes.py::test_gold_cr06_invalid_norm_key_unique_and_json_serializable tests/test_golden_cr_fixes.py::test_gold_cr03_fingerprint_drift_includes_wal_shm tests/test_golden_cr_fixes.py::test_gold_cr04_git_security_audit_uses_git_commands -q` → **3 failed**（`object` 不可 JSON；缺 `compare_fingerprint_bundles`／`git_security_audit`） |
| GREEN | 序列號標記取代 `object()`；指紋前後比含 sidecar；git 稽核寫入 evidence |
| REFACTOR | 無 |
| 本機 REGRESSION | 相關 `test_golden_cr_fixes`＋`test_decimal_text_normalize` → **37 passed**；全量 `uv run pytest -q` → **248 passed／1 skipped**／63.67s；`uv run ruff check .` 通過；正式 DB **未**寫入 |
| 判定 | **有證據 TDD**（見 §6.2 `golden_cr_batch2_v1`）；待獨立複審；Phase 2／Merge／Migration **未**授權 |

### 1.24 GOLD-CR-04／05／10／11 收斂（本任務）

| 項目 | 結果 |
|---|---|
| 分支 | `feature/fifo-same-day-reconciliation`（基線 `4da77f0`） |
| 變更 | `git_security_audit` 檢查 returncode；`classify_capital_csv_row`；`resolve_batches_by_sha256`；交叉核對 trade_type／currency／account／parse_status／列相對序 |
| RED | 4 新測 failed（缺 runner／classify／resolve；交叉缺 trade_type） |
| GREEN | 上列函式＋`analyze_capital_csv`／`cross_check_csv_to_db` 最小接線 |
| REFACTOR | 無 |
| 本機 REGRESSION | `test_golden_cr_fixes` → **28 passed**；全量 `uv run pytest -q` → **252 passed／1 skipped**／64.92s；`uv run ruff check .` 通過；正式 DB **未**寫入 |
| 判定 | **有證據 TDD**（見 §6.2 `golden_cr_batch3_v1`）；PENDING 外部鍵／多帳戶真實樣本維持；Phase 2／Merge／Migration **未**授權 |

### 1.25 GOLD-CR-10 收尾與 Phase 0／1 收斂（本任務）

| 項目 | 結果 |
|---|---|
| 分支 | `feature/fifo-same-day-reconciliation`（基線 `51895c3`） |
| 變更 | invalid／excluded 分計；`csv_acceptance_gate`；交叉有非法列不得 PASS；Phase 0／1 收斂摘要 |
| RED | `test_gold_cr10_invalid_rows_separated_and_block_acceptance` failed（缺分計／gate） |
| GREEN | `build_capital_csv_analysis_from_rows`／gate／cross_check／summary blockers |
| REFACTOR | 無 |
| 本機 REGRESSION | `test_golden_cr_fixes` → **29 passed**；全量 **253 passed／1 skipped**／63.96s；ruff 通過；正式 DB **未**寫入 |
| 判定 | Phase 0／1 基礎開發收尾；待 Owner 確認 Phase 2；Merge／Migration **未**授權 |

### 1.26 Phase 2 獨立 C 層（本任務）

| 項目 | 結果 |
|---|---|
| 分支 | `feature/fifo-same-day-reconciliation` |
| 變更 | `backend/golden/expected_c.py`；`scripts/_golden_phase2_expected_c.py`；HTML／玉山 `invalid_row_count=UNKNOWN`；Phase02／PENDING／STATUS 文件 |
| RED | `tests/test_golden_expected_c.py` 收集期 `ModuleNotFoundError: backend.golden` |
| GREEN | 獨立彙總／CASH Two-Pass／§7 損益；本機 `data/golden/expected_c/`（gitignore） |
| REFACTOR | ruff FURB157（`Decimal(0)`）；無業務行為變更 |
| 本機 REGRESSION | `test_golden_expected_c` → **8 passed**；全量 **261 passed／1 skipped**／74.78s；ruff 通過；正式 DB **未**寫入 |
| 判定 | Phase 2 C 層本機完成；待獨立 Reviewer；CR-10A／Merge／Migration **未**授權 |

### 1.27 Phase 2 複審修正（本任務）

| 項目 | 結果 |
|---|---|
| 分支 | `feature/fifo-same-day-reconciliation` |
| 變更 | trade_id 來源+列號；負數 TRUNC 朝零；帳戶／幣別分池；來源完整性閘門；逐筆 allocation_lines；GOLD-001-2236 |
| RED | 擴充 `test_golden_expected_c` → **9 failed／7 passed**（缺唯一 ID／trunc 公開／integrity／逐筆等） |
| GREEN | 上列契約最小實作；本機 expected_c 重產 |
| REFACTOR | 無大型重構 |
| 本機 REGRESSION | `test_golden_expected_c` → **16 passed**；全量 **269 passed／1 skipped**／81.41s；ruff 通過；正式 DB **未**寫入 |
| 判定 | 複審項已修；待獨立 Reviewer 接 CR-10A；Merge／Migration **未**授權 |

### 1.28 Phase 3／CR-10A 接回（本任務）

| 項目 | 結果 |
|---|---|
| 分支 | `feature/fifo-same-day-reconciliation`（Owner PR #12 Phase 3 授權） |
| 變更 | Phase2 `phase2_exit_code`／`may_mark_full_acceptance`；`report_finance` 負數朝零；`compare_c_d`／`phase3_pipeline`；RED-07 逐筆互抵；`uat_exit_code`；本機 CR-10A UAT 腳本 |
| RED | `test_golden_phase2_exit`／`test_report_finance_trunc_neg`／`test_golden_compare_c_d` 缺實作／負數 `-1.9→-2` |
| GREEN | 上列最小實作；合成 C↔D；真實 GOLD-001-2236 隔離 UAT **PASS**（證據本機 gitignored） |
| REFACTOR | 無大型重構 |
| 本機 REGRESSION | `uv run pytest -q` → **285 passed**／66.31s；`uv run ruff check .` 通過；正式 DB **未**寫入 |
| 判定 | 初版接回；後續複審見 §1.29 |

### 1.29 Phase 3 複審修正（本任務）

| 項目 | 結果 |
|---|---|
| 分支 | `feature/fifo-same-day-reconciliation`（PR #12 Phase 3 複審） |
| 變更 | C `allocation_lines`→Trace 逐筆指紋核對；`open_cost` 觀測／禁填 expected；CR-10B 故障 summary／exit；CR-10C 產物內容；WAL／SHM 指紋；GOLD-004 全年 D |
| RED | per_row 未接 C；open_cost 無條件 0；CR-10B 僅 helper |
| GREEN | `allocation_line_finance_rows`／`compare_allocation_lines_to_trace_rows`；`observe_open_cost_from_detail_xlsx`；UAT／004 腳本 |
| REFACTOR | 無大型重構 |
| 本機 UAT | GOLD-001-2236 **PASS**；GOLD-004 **PASS**（HTML bridge；CSV Parser 仍 PENDING）；正式 DB 指紋 PASS |
| 本機 REGRESSION | `uv run pytest -q` → **288 passed**／65.08s；`uv run ruff check .` 通過；正式 DB **未**寫入 |
| 判定 | 可驗證財務項已收斂；Merge／Migration **未**授權 |

### 1.30 Phase 3 合併前收尾（本任務）

| 項目 | 結果 |
|---|---|
| 分支 | `feature/fifo-same-day-reconciliation`（PR #12 Phase 3 合併前收尾） |
| 變更 | GOLD-004 `decide_gold004_verdict`（必要失敗→FAIL）；CR-10C 守恆實際值／audit 一致性；CR-10A 重複鍵多重集＋列數；CR-10B 故障用實際觀測；Excel 未驗證範圍明示 |
| RED | `tests/test_golden_phase3_wrap.py`：缺 `decide_gold004_verdict`；守恆僅字串存在；重複鍵 dict 覆蓋 |
| GREEN | `decide_gold004_verdict`；`verify_audit_artifacts_content` 強化；`compare_allocation_lines_to_trace_rows` 多重集；UAT 腳本 |
| REFACTOR | 無大型重構 |
| 本機 UAT | GOLD-001-2236 **PASS**（fault 僅 `detail_xlsx_finance_ok`）；GOLD-004 **PASS**（`necessary_ok`；HTML bridge；CSV Parser 仍 PENDING） |
| 本機 REGRESSION | `uv run pytest -q` → **299 passed**／74.81s；`uv run ruff check .` 通過；正式 DB **未**寫入 |
| 判定 | 合併前財務驗收可交 Reviewer；**不得** Merge／正式 Migration／寫正式 DB |

### 1.31 原始 CR-01～13 完整銷帳（本任務）

| 項目 | 結果 |
|---|---|
| 分支 | `feature/fifo-same-day-reconciliation`（PR #12：暫停 Merge Readiness，返回原始 CR） |
| 變更 | 新增 `docs/test/PR12_ORIGINAL_CR_WRITEOFF.md`；CR-06C Trace 利息／稅非零落點斷言；UAT／PENDING 對齊；**GOLD 與原始 CR 分列** |
| 優先核對 | CR-02↔SPEC `tw_sec_tax_v3`；CR-06B Excel；CR-06C Trace 費稅息；CR-10A／B／C 對回 Round-4＋Phase 3 |
| 銷帳摘要 | 無 BLOCKER／OPEN；多數 RESOLVED；02／05／06／06B／06C／10／10A／11／13 為 PASS_WITH_NOTES |
| 本機 REGRESSION | `uv run pytest -q` → **299 passed**／66.52s；`uv run ruff check .` 通過；正式 DB **未**寫入 |
| 判定 | 原始 CR 銷帳表已交；**等待 Reviewer 最終審查**；不得 Merge／Migration／寫正式 DB |

### 1.32 CR-06C 第一片段收尾＋Merge Readiness 實查

| 項目 | 結果 |
|---|---|
| 分支 | `feature/fifo-same-day-reconciliation`（PR #12 Owner：CR-06C 必要收尾＋合併準備） |
| 強化 | Trace `allocation_id`→`sequence_no` 對位第一片段費／稅／息；後續片段必須 0；獨立 C `allocation_lines`＋Excel 買賣手續費／稅；重用 TRUNC 價金守恆 |
| GREEN | `tests/test_fifo_same_day_2236_original_import_e2e.py` **6 passed**；產品碼無變更（行為已正確，驗收強化） |
| 文件 | `PR12_ORIGINAL_CR_WRITEOFF.md` 更新 CR-06C 實際驗收範圍；非零利息維持 PENDING_DATA |
| 本機 REGRESSION | `uv run pytest -q` → **299 passed**／61.38s；`uv run ruff check .` 通過；正式 DB **未**寫入／**未** migrate |
| 判定 | 見 Merge Readiness Report；**等待 Owner 最終授權 Merge** |

### 1.33 測試資料來源與驗收誠信稽核（Merge 暫停）

| 項目 | 結果 |
|---|---|
| 分支 | `feature/fifo-same-day-reconciliation`（PR #12：Merge 前資料誠信稽核） |
| 變更 | 新增 `docs/test/PR12_TEST_DATA_SOURCE_AUDIT.md`；關鍵測試／UAT／fixture 標 `SOURCE:`；CR-06C 非零利息 `pytest.skip` 占位 |
| 十項檢查 | 未發現 INVALID_EVIDENCE／反推 Expected／固定 True 冒充／敏感入 Git；合成 vs REAL_DERIVED 已分列 |
| 本機 REGRESSION | `uv run pytest -q` → **299 passed／1 skipped**／68.28s；`uv run ruff check .` 通過；正式 DB **未**動；**暫停 Merge** |
| 判定 | 稽核表已交；等待 Reviewer 最終確認 |

---

## 2. Git 歷史稽核：測試是否先於實作？

### 已提交（`git log`）

| Commit | 日期 | 內容 |
|---|---|---|
| `f17e068` | 2026-11-20 | `add：初始化專案文件與 Cursor 開發設置`（rules／hooks／初版 PRD／SPEC） |
| `dce0921` | 2026-11-20 | `doc：重寫 PRD 與 SPEC 為 Database-first 架構` |
| `cf4e68e` | 2026-11-20 | **回歸基準**：`add：建立現有功能回歸測試基準版本（非 TDD 完成）`；入庫 `backend/`、`tests/`、`.cursor/rules/tdd-rule.mdc`、`docs/test/TDD_STATUS.md` 等；**非 TDD 完成** |

### 刻意不入庫（機密／真實資料）

由 `.gitignore` 排除：`data/`（含 `trading.db`、`source_archive/`）、`input/`（含真實對帳單）、`output/`、`.env*`、`*.db`。Fixtures 僅合成 HTML。

### 判定

| 問題 | 判定 |
|---|---|
| 是否有「測試 commit 早於功能 commit」？ | **否**。`cf4e68e` 同 commit 同時入庫實作與測試，無分階段 RED→GREEN 序。 |
| 是否有 RED／GREEN／REFACTOR 分階段 commit？ | **否**（針對初版 `cf4e68e` 入庫）。**凍結註**：撰寫本列時 §6.2 為空；其後 §6.2 已填多筆有證據 TDD——**勿**再解讀為「目前仍空」。 |
| 檔案時間線（輔助，非正式 Git 證據） | `backend/` 約 18:24–18:53 寫入；多數 `tests/test_*.py` 約 18:45–18:46；`test_tdd_cli_contract.py` 約 19:10（CLI 已存在後）；`test_db_transactions.py` 約 19:22（功能已存在後補寫）。 |
| 先前 Agent 執行紀錄 | 契約測試**首次對現況執行即 12/12 PASS**；`test_db_transactions` 僅遇一次 **fixture／session 用法錯誤**（`DetachedInstanceError`），修正測試後即 PASS——**非業務行為缺失的 RED**。 |

**結論**：依 `docs/test/TDD.md` 定義，現況應標為**特徵化／回歸測試**，不是已完成的 TDD 開發史。

---

## 3. 分類定義（本專案用法）

| 標籤 | 定義 |
|---|---|
| **契約（Contract）** | 黑箱驗收：經 CLI／公開行為驗證 PRD／SPEC／README 契約 |
| **單元（Unit）** | 直接呼叫純函式或窄模組，無完整 CLI 子程序 |
| **整合（Integration）** | 跨 DB／匯入／配對／報表多層，但仍用 `tmp_path` |
| **回歸／特徵化（Regression）** | 功能已存在後補寫、鎖定現況行為；**初次執行即預期通過** |
| **有證據的 TDD** | 有紀錄：先失敗測試（RED）→ 最小實作（GREEN）→ 重構後全綠（REFACTOR），且可對到 Git commit 或同等不可竄改證據 |

同一測試可同時標「契約／單元／整合」＋「回歸」。**有證據的 TDD** 必須單獨成立，不得因檔名含 `tdd` 自動套用。

---

## 4. 全部 34 測試分類

### 4.1 CLI 契約（12）— `tests/test_tdd_cli_contract.py`

皆為黑箱契約，且屬**事後／並存實作後的回歸**；**無 RED 證據**。

| ID | 測試函式 | 層級 | TDD 生命週期 | 本次結果 | SPEC 對照 |
|---|---|---|---|---|---|
| 01 | `test_01_preview_does_not_insert_trades` | 契約＋整合 | 回歸（非 TDD） | PASS | 匯入預覽 |
| 02 | `test_02_html_xls_is_normalized_and_summary_row_excluded` | 契約＋整合 | 回歸 | PASS | ING-01/02、NORM-01 |
| 03 | `test_03_same_file_same_account_import_is_idempotent` | 契約＋整合 | 回歸 | PASS | DB-01 |
| 04 | `test_04_identical_real_executions_are_not_collapsed` | 契約＋整合 | 回歸 | PASS | DB-02 |
| 05 | `test_05_source_is_unchanged_after_apply` | 契約＋整合 | 回歸 | PASS | 來源完整性 |
| 06 | `test_06_fifo_one_sell_consumes_two_buys_and_preserves_fees` | 契約＋整合 | 回歸 | PASS | FIFO-02、FEE-02 |
| 07 | `test_07_one_buy_split_by_two_sells_fee_occurs_once` | 契約＋整合 | 回歸 | PASS | FIFO-03、FEE-01 |
| 08 | `test_08_report_has_only_23_typed_columns_and_no_total_or_formula` | 契約＋整合 | 回歸 | PASS | REP-01/02/04 |
| 09 | `test_09_unmatched_earlier_sell_blocks_final_but_allows_draft` | 契約＋整合 | 回歸 | PASS | FIFO-04、AUD-01 |
| 10 | `test_10_fifo_never_matches_buys_from_different_accounts` | 契約＋整合 | 回歸 | PASS | FIFO-06 |
| 11 | `test_11_second_report_must_not_overwrite_first` | 契約＋整合 | 回歸 | PASS | REP-07 |
| 12 | `test_12_backup_is_a_consistent_sqlite_database` | 契約＋整合 | 回歸 | PASS | AUD-02 |

### 4.2 單元／整合（22）

| 檔案 | 測試 | 層級 | TDD 生命週期 | 本次 | SPEC |
|---|---|---|---|---|---|
| `test_detector.py` | `test_detect_html_pseudo_xls` | 單元 | 回歸 | PASS | ING-01 |
| `test_detector.py` | `test_detect_csv_utf8` | 單元 | 回歸 | PASS | ING-03（部分） |
| `test_fifo.py` | `test_partial_sell` | 單元 | 回歸 | PASS | FIFO-01 |
| `test_fifo.py` | `test_one_sell_two_buys` | 單元 | 回歸 | PASS | FIFO-02 |
| `test_fifo.py` | `test_sell_before_buy_insufficient` | 單元 | 回歸 | PASS | FIFO-04 |
| `test_fifo.py` | `test_no_cross_symbol` | 單元 | 回歸 | PASS | FIFO-06 |
| `test_fifo.py` | `test_order_ambiguity_same_day`（改寫：庫存優先、不標 ORDER_AMBIGUITY） | 單元 | TDD（本輪） | PASS | FIFO-05 |
| `test_fifo.py` | Case1–10／1589／忽略 trade_time 解套 | 單元 | TDD（本輪） | PASS | FIFO-05/06/07/08 |
| `test_fee_once.py` | `test_fee_once_on_split_fragments` | 單元 | 回歸 | PASS | FEE-01/02 |
| `test_normalizer.py` | `test_preview_excludes_totals_and_counts` | 整合 | 回歸 | PASS | ING-02 |
| `test_normalizer.py` | `test_symbol_kept_as_text` | 單元 | 回歸 | PASS | NORM-01 |
| `test_import_idempotency.py` | `test_reimport_same_file_no_new_trades` | 整合 | 回歸 | PASS | DB-01 |
| `test_opening_lots.py` | `test_opening_lot_covers_early_sell` | 單元 | 回歸 | PASS | 期初庫存 |
| `test_report_schema.py` | `test_headers_and_types` | 單元 | 回歸 | PASS | REP-01/04 |
| `test_report_no_totals.py` | `test_no_total_row` | 單元 | 回歸 | PASS | REP-02 |
| `test_report_no_totals.py` | `test_empty_only_header` | 單元 | 回歸 | PASS | REP-03 |
| `test_db_transactions.py` | `test_foreign_keys_pragma_is_on` | 單元 | 回歸 | PASS | §11 / DB-03 |
| `test_db_transactions.py` | `test_orphan_account_insert_is_rejected` | 單元 | 回歸 | PASS | DB-03 |
| `test_db_transactions.py` | `test_trade_check_constraint_rejects_invalid_side` | 單元 | 回歸 | PASS | DB-03 |
| `test_db_transactions.py` | `test_mid_transaction_error_rolls_back_without_polluting` | 整合 | 回歸 | PASS | DB-03 |
| `test_db_transactions.py` | `test_wal_or_default_journal_is_usable` | 單元 | 回歸 | PASS | §11 |
| `test_end_to_end.py` | `test_e2e_sample_with_partial_report` | 整合 | 回歸 | PASS | 匯入→配對→DRAFT |
| `test_end_to_end.py` | `test_e2e_fee_fixture_clean` | 整合 | 回歸 | PASS | FEE／報表 |

### 4.3 有證據的 TDD 測試

| 統計 | 數量 |
|---|---|
| 有完整 RED→GREEN→REGRESSION Git 證據 | **6 功能** — 上列五項 ＋ `pr7_fifo_cr_fixes_v1`（見 §6.2；Commit SHA 以本輪提交為準） |
| 有 RED→GREEN→REGRESSION 執行證據、**未**入庫 Commit | **1 功能** — `fragment_gross_trunc_v1`（見 §6.2） |
| 本機整合後補充覆蓋（非 Cloud 原始 RED） | **2** — 融資／配股＋`raw_rows`／來源核對區分 |
| 僅回歸／特徵化 | **34** |

### 4.4 玉山 TDD 測試（12）— 合成測資

| 檔案 | 測試 | 層級 | TDD 生命週期 | SPEC |
|---|---|---|---|---|
| `test_esun_xlsx_parser.py` | `test_esun_profile_exists` 等 6 | 單元／整合 | 有證據 TDD | ING-05/06/07、NORM-04 |
| `test_esun_xlsx_parser.py` | `test_unsupported_trade_type_becomes_exception_not_silent_drop` | 整合 | Cloud Agent TDD（`fb8d5f2`） | NORM-03、FR-02 |
| `test_esun_xlsx_parser.py` | `test_unsupported_trade_types_surface_as_errors_*`／`*_persist_as_raw_row_errors` | 整合 | **本機補充**（對 Cloud GREEN 已綠；非原始 RED） | NORM-03、ING-08 區分 |
| `test_esun_xlsx_import.py` | `test_preview_source_totals_reconcile` 等 3 | 整合 | 有證據 TDD | ING-08、DB-03 對齊 |

### 4.5 現沖 DAY_TRADE TDD 測試（新增）

| 檔案 | 測試 | 層級 | SPEC |
|---|---|---|---|
| `test_day_trade_normalize.py` | 現沖 BUY／SELL、費用保留、未知類型、合成 5 筆全 ok／入庫 | 單元／整合 | NORM-05 |
| `test_day_trade_fifo.py` | 同日無序先賣後買、多筆 FIFO、不占 CASH、不跨日、費用一次 | 單元 | FIFO-07/08、FEE |

---

## 5. SPEC §12 覆蓋缺口（誠實對照）

已有測試覆蓋的重點：ING-01/02、ING-05～08、NORM-01、NORM-04/05、DB-01/02/03（基本）、FIFO-01～08、FEE-01/02、REP-01～04/07、AUD-01/02。

仍弱或未見獨立自動化案例（不虛構通過）：

| SPEC ID | 狀態 |
|---|---|
| ING-03 CP950／未知編碼 | 僅 UTF-8 偵測；CP950／錯誤編碼未完整覆蓋 |
| ING-04 真 XLS／XLSX（通用） | 玉山路徑覆蓋真 XLSX；通用 OLE／非玉山 XLSX 仍無獨立案例 |
| NORM-02 千分位／禁 float | 未見獨立斷言 |
| NORM-03 未支援類型／壞日期 | 玉山融資／配股已有 preview／raw_rows／來源核對區分；通用 HTML／壞日期仍弱 |
| ING-08 頁尾含未支援列時 | **已對齊文件**（PRD §2.3／SPEC §4.2.1／ING-08）：未支援不計入 `recognized_*` → `matched=false`；自動化見本機補充測試 |
| FEE-03／FEE-06／AUD-06 TRUNC±1／超限 | **已覆蓋**（`test_fragment_gross_trunc.py` 案 A／B／±1／±2／禁比例餘額法） |
| FEE-04／FEE-05／AUD-04／AUD-05 | **已覆蓋**（`test_uat_finance_conservation.py` UAT-01～22；UAT-22 期望已對齊 TRUNC） |
| REP-05／REP-06 無 Excel／公式注入 | 契約有「無公式」部分；注入字串案例不足 |
| AUD-03 同版 FIFO 可重現且舊 run 不覆寫 | **後補（2026-11-22）**：已由 `tests/test_fifo_cr_fixes.py`／§6.2 `pr7_fifo_cr_fixes_v1` 覆蓋；本列原「未見獨立斷言」為 PR7 前快照 |

新增上述缺口時，**必須先 RED**（見 `docs/test/TDD.md`），不得直接補綠燈測試並宣稱 TDD。

---

## 6. 功能 TDD 生命週期追蹤

> 僅在**確實發生**該階段時填寫。禁止回填虛構的失敗結果或假 commit。
> Commit 欄填短 SHA。

### 6.1 既有功能（歷史——非 TDD）

| 功能／規則 | RED | GREEN | REFACTOR | 全量 pytest | 判定 |
|---|---|---|---|---|---|
| P0 匯入／FIFO／明細／CLI（初版實作） | 無證據 | 無分階段證據 | 無證據 | 事後全綠（34）；基準 `cf4e68e` | **特徵化／回歸** |
| CLI 契約 01–12 | 首次對現況執行即 PASS；無失敗紀錄 | 不適用（無先紅） | 不適用 | 含於 34 passed | **回歸契約** |
| `test_db_transactions`（2026-11-20 補） | 僅測試寫法錯誤一次；**非**業務 RED | 功能已存在；測通即綠 | 未做結構重構 | 補測後 34 passed | **回歸** |

### 6.2 有證據的 TDD 条目

| 功能 ID | 說明 | RED（日期／指令／失敗摘要／commit） | GREEN（日期／最小變更／commit） | REFACTOR（日期／變更摘要／commit） | REFACTOR 後全量 pytest | 備註 |
|---|---|---|---|---|---|---|
| `esun_xlsx_v1` | 玉山真 XLSX：日期繼承、次列代號、四類型、小計排除、來源核對、現沖不進 FIFO（當時規格） | 2026-11-20；`uv run pytest tests/test_esun_xlsx_*.py -v`；**8 failed / 1 passed**；失敗為 `ProfileError`／`ModuleNotFoundError`；commit `adb6fcc` | 2026-11-20；commit `1199e55`；9 passed | 2026-11-20；commit `b2b7dc1` | **43 passed** | 規格 `5ade9a8`；當時 Preview：63 ok／2 現沖 error（已被 `day_trade_v1` 覆寫行為，本列不改寫歷史） |
| `day_trade_v1` | 現沖改為 DAY_TRADE 可入庫；同日無序 FIFO（含先賣後買）；不占 CASH | 2026-11-20；`uv run pytest tests/test_day_trade_*.py tests/test_esun_xlsx_*.py -v`；**12 failed / 6 passed**；缺 `trade_type_map`、現沖仍 `DAY_TRADE_UNSUPPORTED`、同日 `ORDER_AMBIGUITY`／跨日誤配；commit `6e473ab` | 2026-11-20；schema／profile／normalizer／同日 DAY_TRADE FIFO／報表標籤；commit `e72f8b5` | GREEN 已抽出 `_run_day_trade_group` 等；另 `5a57791` 穩固費用斷言；無獨立 restruct commit | **52 passed** | 規格 `d24c966`；Preview：65 ok／0 error；matched；來源與正式 DB 未改 |
| `esun_unsupported_rows_v1` | 玉山非四種交易類別（如融資）不得靜默丟棄；須進 `UNSUPPORTED_TRADE_TYPE` | 2026-11-20；Cloud Agent；`uv run pytest …::test_unsupported_trade_type_becomes_exception_not_silent_drop -v`；**1 failed**；`error_count == 0`（融資列被 skip）；commit `fb8d5f2` | 2026-11-20；Cloud Agent；非結構首欄列仍輸出扁平列；**僅四種已支援類型**計入 `recognized_*`；commit `a0df837` | 無獨立 restruct | Cloud 當下 **53 passed**（doc `592e1a5`） | Bugbot Medium；SPEC 補「未支援成交列」 |
| `esun_unsupported_local_coverage` | 本機補充：融資＋配股、apply→`raw_rows`、頁尾含未支援時核對區分 | **非 RED**：Cloud GREEN 已存在後補測；不得冒充 Cloud 原始 RED | 無新 parser 行為（沿用 `a0df837`） | 無 | 整合後 **55 passed** | 測試 commit `7a3a2f8`；fixture／斷言擴充 |
| `esun_fifo_finance_v1` | 部分配對賣出價金含未配對殘量；收入扣利息；配套 FIFO／未配對明細；exceptions／audit 價金守恆欄；W 殘量註記 | 2026-11-21；`uv run pytest tests/test_uat_finance_conservation.py -v`；**10 failed / 12 passed**；業務失敗含收入 93585≠46585、未扣利息 14970≠14962.50、缺 `project_fifo_trace_rows`／`report_finance`、缺 W 註記；commit `65f4459`（規格 `03a2918`） | 2026-11-21；`detail_projector` 賣出 `_split_gross` 納殘量、`income` 扣息、W 註記；`report_finance`／`fifo_trace_writer`／`conservation_writer`；`report_service` 強化 audit；commit `71e21a7`；UAT 22 passed | GREEN 已抽出 `report_finance`（split／income／enrich）；無獨立 restruct commit | **77 passed** | RCA `docs/test/RCA_esun_fifo_finance.md`；隔離 E2E 見產出目錄，不覆寫舊 DRAFT |
| `fragment_gross_trunc_v1` | 片段價金改 `TRUNC(qty×unit_price)`；`|diff|≤1` 調最後片段；超限發 `AMOUNT_CONSERVATION_OUT_OF_TOLERANCE`；廢止比例／餘額法；維持 A～W | 2026-11-21；`uv run pytest tests/test_fragment_gross_trunc.py …uat22 -q`；**8 failed / 6 passed**；投影仍呼叫已廢止 `split_gross`（比例／餘額）→ `RuntimeError`；UAT-22 期望改為 TRUNC 13332／13947 | 2026-11-21；`allocate_trade_fragment_amounts`；`detail_projector`／`conservation_writer`／`report_service` 改用 TRUNC＋audit 超限；commit `fix: apply TRUNC fragment pricing with bounded residual reconciliation` | 無獨立 restruct | **90 passed** | 規格 SPEC §7.3／PRD FR-05；隔離 E2E `output/uat_esun_trunc/`；人工 UAT 已通過；守恆 65/65／超限 0 |
| `capital_html_finance_regression_v1` | 群益 `statement_html_v1` 合成路徑：防 HIST-01 部分配對吃全額、費用一次、利息扣減、早賣 DRAFT／exceptions 守恆欄、A～W | **非 RED**：RCA 確認現況已正確後補測；首次執行即 **4 passed**；不得冒充業務 RED；測試 commit `d8d9578` | 無新業務碼（沿用 `report_finance`／projector） | 無 | **94 passed** | RCA／STATUS doc `453e0e0`；測試 `tests/test_capital_html_finance_regression.py` |
| `cash_prior_inventory_fifo_v1` | CASH 同日改採開盤前庫存優先沖減；移除缺序 `ORDER_AMBIGUITY`；DAY_TRADE 不變；1589 合成回歸 | 2026-11-22；`uv run pytest tests/test_fifo.py -q`；**12 failed / 5 passed**；`ORDER_AMBIGUITY` 短路／time 解套；commit `adcadf5` | 2026-11-22；`detect_order_ambiguity` 回空；`_run_cash_group` 按日先賣後買；commit `22662be` | GREEN 已抽出 `_cash_day_sort_key`；無獨立 restruct | **106 passed** | 規格／STATUS `8babf7d`；正式 DB 未動 |
| `pr7_fifo_cr_fixes_v1` | CR-01 版本追溯、CR-02 期初守恆、CR-03 fingerprint、CR-04 SQLite 整合；真實副本 UAT | 2026-11-22；`uv run pytest tests/test_fifo_cr_fixes.py tests/test_fifo_sqlite_integration.py -q`；**9 failed／5 passed**；版本／opening 守恆／fingerprint；commit `33f2222` | 2026-11-22；`ALGORITHM_VERSION`、`quantity_conservation(opening_lots=…)`、`build_audit`、fingerprint 欄位、backup ro；commit `60d3446` | 無獨立 restruct | **120 passed** | UAT／規格 doc `07b5f4b`；正式 DB 未動 |
| `fifo_v3_two_pass_same_day_v1` | CASH Pass2 同日補沖銷；`match_type`；Independent day-trade annotation；2236 合成配平 | 2026-11-26；目標測 **9 failed／3 passed**（blocking／缺 `match_type`／annotation stub／版本 v2） | 2026-11-26；Pass2＋`match_type`＋annotation＋migration＋版本 v3；工作區尚未 commit | 無獨立 restruct | **128 passed** | RCA `docs/test/RCA_two_pass_fifo_same_day.md`；正式 DB 未動；Commit 待授權 |
| `pr12_cr_fixes_v1` | PR #12 CR：annotation 稅證據／支持股數／AMBIGUOUS／例外隔離；migration backfill；report ON／OFF；2236 E2E；UAT 目錄／verdict | 2026-11-26；`tests/test_day_trade_annotation.py` **5 failed／7 passed**（業務缺口） | 2026-11-26；annotation／migration／report／UAT／E2E／matcher 邊界；工作區尚未 commit | docstring（無行為變更） | **145 passed** | 正式 DB 未動；Commit／PR 回覆待授權 |
| `pr12_cr_r2_v1` | PR #12 Round-2：稅適用範圍／annotation prep 邊界／原始九筆 import E2E／migration FK／Excel ON-OFF／UAT WAL＋獨立 out／CR-12 ids | 2026-11-26；目標測 **7 failed／15 passed**（ETF／未知／生效日前仍 HALF；缺欄；prep 未隔離） | 2026-11-26；`tw_sec_tax_v2`；report prep 邊界；original import E2E；UAT／migration 強化；工作區尚未 commit | 無獨立 restruct | **153 passed** | 正式 DB 未動；Commit／PR 回覆待授權 |
| `pr12_cr_r3_v1` | PR #12 Round-3：inferred 分類＋稅有效窗 v3／原始 E2E 強化／`build_uat_checks` 反向／非干涉嚴格／migration 財務欄／指紋文件 | 2026-11-26；先寫 RED 契約測（inferred／valid_through／verdict 反向／REQUIRED_AUDIT_KEYS／permutation） | 2026-11-26；`tw_sec_tax_v3`；`build_uat_checks`；E2E／非干涉／migration；工作區尚未 commit | docstring（無行為變更） | **180 passed**／64.28s | 正式 DB 未動；ruff 通過；Commit／PR 回覆待授權 |
| `pr12_cr_r4_v1` | PR #12 Round-4：Excel 真實財務驗證／檔案層故障注入／Owner 列序／permutation 財務／Trace 逐筆費用／稅期間＋MIXED | **事後驗證**：未留存獨立 RED 失敗輸出；新增 `test_uat_fifo_same_day_file_fault` 等 | 2026-11-26；UAT finance verify／resolve outputs；annotation MIXED；E2E helpers；工作區尚未 commit | 無獨立 restruct | **205 passed**／78.18s | 正式 DB 未動；ruff 通過；Commit／PR 回覆待授權 |
| `cr10a_finance_verify_v1` | CR-10A：cost／income／qty／interest 獨立 Decimal golden 核對＋`min_detail_rows` 結構下限；禁單列灌總額 | 2026-11-26；`-k "cost_income_both_up … single_row_fake …"` → **6 failed／1 passed**（cost±1＋income±1 仍 ok；qty 竄改仍 ok；單列仍 ok；golden 缺鍵） | 2026-11-26；擴充 golden；`verify_detail_xlsx_finance` 獨立比對＋結構；多列正向；工作區尚未 commit | 無獨立 restruct | **211 passed／1 skipped**／83.85s | 正式 DB 未動；ruff 通過；**待複審**；Commit／PR 待授權 |
| `golden_phase01_inventory_v1` | Phase 0／1 黃金驗收：Decimal 文字正規化匿名測＋盤點腳本／非敏感 Manifest 模板與規範文件；真實 Manifest／evidence 本機 gitignored | **非業務 RED**：正規化為盤點交叉核對基礎建設；匿名測首次即對齊實作 | 2026-11-26；`backend/util/decimal_text.py`；`scripts/_golden_phase01_inventory.py`（唯讀）；`docs/test/GOLDEN_ACCEPTANCE_PHASE01.md` | 無獨立 restruct | **222 passed／1 skipped**／66.79s | 正式 DB 未寫入；ruff 通過；**CR-10A 仍未結案**；Phase 2 未授權；Commit／Push 待複審 |
| `golden_cr_01_06_07_08_09_v1` | GOLD-CR：日期真實排序、非法 Decimal fail-closed、千分位／±0、SHA256 鎖定阻礙、盤點失敗非零結束碼；PENDING_DATA 文件 | 2026-11-26；`tests/test_golden_cr_fixes.py` 收集期缺模組 → ERROR／既有非法數值契約需改 | 2026-11-26；`date_text`／`sha256_lock`／強化 `decimal_text`；inventory 結束碼 | 無獨立 restruct | **231 passed／1 skipped**／74.94s | 正式 DB 未寫；CR-10A 仍開；待資料項見 `PENDING_DATA_VALIDATION.md` |
| `golden_cr_06_07_r2_v1` | GOLD-CR-06／07 複審：`is_finite` 拒 NaN／Inf；非法不回 sentinel；千分位先驗證再去逗號 | 2026-11-26；擴充 `test_golden_cr_fixes`（非有限／非法千分位／相同非法不得相等） | 2026-11-26；`decimal_text`＋`nums_equal`／`_norm_num_key` | 無 | **245 passed／1 skipped**／66.35s | 01／08／09／PENDING 文件不重開；Phase 2 未授權 |
| `golden_cr_batch2_v1` | 第二批：非法 Decimal 鍵可 JSON 序列化；GOLD-CR-03 WAL／SHM 指紋前後比；GOLD-CR-04 實際 git ls-files 稽核 | 2026-11-26；3 新測 **failed**（object 不可序列化；缺比較／稽核函式） | 2026-11-26；`_norm_num_key`／`compare_fingerprint_bundles`／`git_security_audit` | 無 | **248 passed／1 skipped**／63.67s | 01／06核心／07／08／09 不重開；PENDING 維持；Phase 2 未授權 |
| `golden_cr_batch3_v1` | CR-04 returncode；CR-10 列合法性；CR-11 批次歧義；CR-05 可立即核對欄 | 2026-11-26；4 新測 **failed** | 2026-11-26；audit／classify／resolve／cross_check 擴充 | 無 | **252 passed／1 skipped**／64.92s | 03／06 結案不重開；PENDING 外部鍵／多帳戶真實樣本 |
| `golden_cr10_close_v1` | CR-10：invalid／excluded 分計；非法列阻擋完整驗收；Phase 0／1 收斂文件 | 2026-11-26；分計／gate 測 **failed** | 2026-11-26；`build_capital_csv_analysis_from_rows`／`csv_acceptance_gate` | 無 | **253 passed／1 skipped**／63.96s | 04 結案；HTML／玉山 invalid 擴充仍 PENDING |
| `golden_phase2_expected_c_v1` | Phase 2：獨立 C（A＋SPEC）；GOLD-001～004 本機答案；HTML／玉山 invalid→UNKNOWN | 2026-11-26；`test_golden_expected_c` 收集 **ERROR**（缺 `backend.golden`） | 2026-11-26；`expected_c` 模組＋phase2 腳本＋inventory UNKNOWN | ruff Decimal(0) | **261 passed／1 skipped**／74.78s | 真實答案 gitignored；CR-10A／Merge／Migration 未授權；待獨立 Reviewer |
| `golden_phase2_r2_v1` | Phase 2 複審：唯一 trade_id、負數 TRUNC、帳戶／幣別隔離、來源閘門、逐筆 lines、GOLD-001-2236 | 2026-11-26；**9 failed／7 passed** | 2026-11-26；expected_c＋phase2 腳本重產 | 無 | **269 passed／1 skipped**／81.41s | 受測 report_finance 負數 TRUNC 仍 PENDING；真實答案未入 Git |
| `golden_phase3_cr10a_v1` | Phase 3：exit 碼／TRUNC-NEG／C↔D／RED-07／CR-10B exit／本機 2236 UAT | 2026-11-26；exit／trunc／compare 缺模組或負數離零 | 2026-11-26；phase2 exit＋report_finance＋compare／pipeline＋UAT 腳本 | ruff B023 | **285 passed**／66.31s | 真實答案／runs_d 本機；Merge／Migration 未授權 |
| `golden_phase3_wrap_v1` | Phase 3 合併前：GOLD-004 必要失敗→FAIL；CR-10C 守恆實際值；CR-10A 重複鍵多重集；CR-10B 觀測非固定 True | 2026-11-26；`test_golden_phase3_wrap` ImportError／契約 failed | 2026-11-26；`decide_gold004_verdict`＋artifacts／compare／UAT | 無 | **299 passed**／74.81s | GOLD-001／004 UAT PASS；CSV Parser 仍 PENDING；Merge／Migration 未授權 |

**記錄欄位最低要求**

- **RED**：會失敗的測試名稱、`pytest` 指令、失敗原因（斷言／例外）、測試 commit SHA（若已入庫）。
- **GREEN**：為讓該測試通過而改的檔案摘要、功能 commit SHA；**禁止**刪除或弱化驗收斷言。
- **REFACTOR**：結構改善說明、commit SHA；完成後必須 `uv run pytest`（全量）且維持既有斷言強度。

---

## 7. 強制流程（自本稽核起）

對任何**新增功能**或 **Bug 修復**：

- **測試方法**：完整政策見 `docs/test/TDD.md`。
- **端到端交付**：見 `docs/DEVELOPMENT_WORKFLOW.md`（Commit→Push→PR→GitHub CI→Review→UAT→Merge）。

TDD 摘要（與 `docs/test/TDD.md` 一致：**RED → GREEN → REFACTOR → REGRESSION**）：

1. **RED**：先寫／擴充分會因「預期行為尚未實現」而失敗的測試；執行並保存失敗輸出。
2. **GREEN**：只做最小實作使該測試通過；不得為綠燈刪減斷言。
3. **REFACTOR**：可改善設計；不得改變既有業務行為；相關測試必須保持通過。
4. **REGRESSION**：提交前執行完整 `uv run pytest -q`；必須全部通過；更新本檔真實結果與 Commit。
5. 於 §6.2 登錄 **RED → GREEN → REFACTOR → REGRESSION** 四階段結果與 Git commit。
6. 測試只准使用合成資料與 `tmp_path`／臨時 DB；**禁止**讀寫 `data/trading.db`、真實 `input/` 附件、正式 `output/` 報表，也禁止把真實對帳單提交進 Git。

**防混淆**：本機 pytest／REGRESSION ≠ GitHub CI Success ≠ 人工 UAT。
`TDD_STATUS.md` 只記錄實際執行結果，不得把計畫中的測試寫成已通過。

既有 34 項繼續作為回歸門檻；它們的存在**不構成**歷史 TDD 完成證明。回歸基準 Commit：`cf4e68e`。玉山功能以 §6.2 為準。

---

## 8. 執行方式

```powershell
cd C:\Users\billh\python_test\trading_report
uv sync
uv run pytest tests/test_tdd_cli_contract.py -q -x --tb=short
uv run pytest tests/test_esun_xlsx_parser.py tests/test_esun_xlsx_import.py -q
uv run pytest -v --tb=line
```

詳見 `docs/test/TDD.md` §4。

---

## 9. 稽核變更紀錄

| 日期 | 動作 |
|---|---|
| 2026-11-20 | 初建狀態檔（僅列契約 PASS，未區分 TDD／回歸）。 |
| 2026-11-20 | **本稽核**：實跑 34 PASS；Git 僅文件 commit；程式／測試未入庫；全數標為回歸；新增生命週期追蹤與強制 RED 政策；不製造假 RED、不破壞既有實作。 |
| 2026-11-20 | **回歸基準入庫** `cf4e68e`：新增 `.cursor/rules/tdd-rule.mdc`；提交程式／測試／文件；排除真實 DB／對帳單／報表；`statement_sample.html` 改為合成測資。此 commit **不是** TDD 完成標記。 |
| 2026-11-20 | **文件架構整理**：建立 `docs/test/TDD.md` 為唯一正式規範；`tdd-rule.mdc` 改為強制引用；移除 `.cursor/TDD_GUIDE.md`（內容已整併）；更新契約測試過時註解；本檔補記基準 Commit `cf4e68e` 並修正「尚未入庫」等過時描述。 |
| 2026-11-20 | **`esun_xlsx_v1` TDD**：分支 `feature/esun-xlsx-parser`；規格 `5ade9a8` → RED `adb6fcc`（8 failed）→ GREEN `1199e55` → REFACTOR `b2b7dc1`；全量 **43 passed**；真實玉山僅 Preview，未入正式 DB。 |
| 2026-11-20 | **`day_trade_v1` TDD**：規格 `d24c966` → RED `6e473ab`（12 failed）→ GREEN `e72f8b5` → 斷言穩固 `5a57791`；全量 **52 passed**；Preview 65 ok／0 error；未 apply／migrate 正式 DB。 |
| 2026-11-20 | **Cloud Agent `esun_unsupported_rows_v1`**：RED `fb8d5f2`（融資靜默消失）→ GREEN `a0df837`（候選列輸出／未支援不計 recognized）→ doc `592e1a5`；全量 **53 passed**。 |
| 2026-11-21 | **本機整合**：`feature/esun-xlsx-parser` fast-forward 合併上述 3 commits；保留 Cloud 歷史；另補融資／配股／`raw_rows`／來源核對區分（`7a3a2f8`，**非** Cloud RED 回填）；全量 **55 passed**；未 Push／Merge PR／改正式 DB。 |
| 2026-11-21 | **合併前文件對齊**：修訂 PRD §2.3、SPEC §4.2.1／ING-08、README、本檔缺口列；區分候選列／已正規化／未支援／來源核對；全量 **55 passed**；**未** Push／Merge／寫正式 DB；文件變更待使用者確認後再 commit／push。 |
| 2026-11-21 | **`esun_fifo_finance_v1` TDD**：RCA → 規格 `03a2918` → RED `65f4459`（10 failed）→ GREEN `71e21a7`；全量 **77 passed**；未改正式 DB／未覆寫舊 UAT DRAFT；隔離 E2E 另產時間戳檔後停等人工 UAT。 |
| 2026-11-21 | **`fragment_gross_trunc_v1` TDD**：SPEC §7.3／PRD FR-05 → RED 8 failed（禁 `split_gross`）→ GREEN `allocate_trade_fragment_amounts`；全量 **90 passed**；隔離 E2E 守恆 65/65／超限 0；人工 UAT 已通過；Commit `fix: apply TRUNC fragment pricing with bounded residual reconciliation`（不 squash／amend 既有 4 筆）。 |
| 2026-11-21 | **群益 Phase 1 RCA**：`RCA_capital_fifo_finance.md`；隔離 `uat_capital`；現況無必修 Bug；HIST-01 僅舊 DRAFT 高估 22995。 |
| 2026-11-21 | **`capital_html_finance_regression_v1`**：合成 HTML 回歸 4 案（防 HIST-01／費用／利息／早賣 DRAFT）；**特徵化／非 RED**；測試 `d8d9578`／doc `453e0e0`；全量 **94 passed**；未改正式程式／正式 DB；未納入 `.cursor/plans/`、`esun_local_changes.patch`、`scripts/`。 |
| 2026-11-21 | **GitHub Actions pytest CI**：分支 `feature/github-actions-pytest`；新增 `.github/workflows/pytest.yml`（`pull_request`／`push`→`master`；`permissions.contents: read`；`persist-credentials: false`；`uv sync --locked --dev`＋`uv run --locked pytest -q`）；本機 REGRESSION **94 passed**／65.52s；稽核測試僅合成／`tmp_path`、無真實資料上傳、無 FIFO／財務斷言放寬；後經 PR **#5** 合併至 `master`（Merge `92f5ab3`）；CI 於 PR／master 成功。 |
| 2026-11-21 | **品質開發流程文件**：分支 `docs/quality-development-workflow`；新增 `docs/DEVELOPMENT_WORKFLOW.md` 與 `.cursor/rules/dev-workflow-rule.mdc`；PRD §14／SPEC §13＋§16／TDD／README／本檔／`commit-rule.mdc` 增量引用；`py-env.mdc` 對齊 Python **3.11**；本機 REGRESSION **94 passed**／60.03s；**未**改業務碼／Workflow YAML；Commit `461fd37` → **已** Push → **PR #6**（目標 `master`）→ GitHub CI **Success** → Code Review **PASS WITH NOTES**；**Merge 尚未**執行。 |
| 2026-11-21 | **PR #6 Review NOTES 文件修正**：Commit `2176c42` — `doc：修正 PR #6 品質流程審查意見`（已完成）；① `DEVELOPMENT_WORKFLOW` §2.4／§3 統一 Agent **禁止 Force Push（無例外）**；② PRD／SPEC 頁首 metadata 改以 blockquote 空行分段（GFM 分行且避免 `git diff --check` 行尾空白警告）；③ 本檔 §1.11／§7／§9 對齊 Push／PR／CI／Review 實況且不預先寫 Merge；④ §7「三階段」改為 **RED→GREEN→REFACTOR→REGRESSION** 四階段；未改業務碼／測試／CI YAML；未 amend／rebase `461fd37`；**已** Push → PR #6 → CI Success → Code Review **PASS WITH NOTES**；**Merge 尚未**執行。 |
| 2026-11-21 | **PR #6 殘餘 N1／N2 文件對齊**（工作區；不預寫尚未產生之 Commit SHA）：① 本檔 §1.11／§9 對齊真實狀態（`461fd37`＋`2176c42`、已 Push、PR #6、CI Success、Code Review PASS WITH NOTES、Merge 尚未）；② `.cursor/rules/dev-workflow-rule.mdc` Force Push 改為無例外措辭，與 `DEVELOPMENT_WORKFLOW.md` 一致；未改業務碼／測試／CI YAML；未 amend／rebase 既有 Commit。 |
| 2026-11-22 | **`cash_prior_inventory_fifo_v1` TDD**：分支 `feat/cash-prior-inventory-fifo`；RED 12 failed（`ORDER_AMBIGUITY`／time 解套）→ GREEN 按日先賣後買；全量 **106 passed**／76.53s；SPEC／PRD／README／FIFO-05 對齊；正式 DB **未** apply／migrate；未納入 `.cursor/plans/`、`esun_local_changes.patch`、`scripts/`。 |
| 2026-11-22 | **`pr7_fifo_cr_fixes_v1` TDD**：RED 9 failed → GREEN 版本／守恆／fingerprint／SQLite IT；全量 **120 passed**／65.16s；副本 UAT（基準＠`77f3ed7`）1589 通過、`ORDER_AMBIGUITY` 不再於新 run 出現；正式 DB **未**動；未納入 `.cursor/plans/`、`esun_local_changes.patch`、`scripts/`、`data/uat/`。 |
| 2026-11-22 | **歷史文件一致性 Phase B**：分支 `docs/history-standardization-phase-b`；修正 SPEC／PRD 過時狀態與欄 E、README UAT 隔離範例、BUGBOT 斷鏈改指針、TDD 導覽、Workflow §8 文件慣例、Class C 橫幅；**未**改業務碼／財務演算法／CI YAML；正式 DB **未**動；未納入 `.cursor/plans/`、`esun_local_changes.patch`、`scripts/`。REGRESSION 見 §1.14。 |
| 2026-11-26 | **`fifo_v3_two_pass_same_day_v1` TDD**：分支 `feature/fifo-same-day-reconciliation`；Gate2 契約變更（FIFO-05 Pass2）；RED 9 failed → GREEN Pass2／annotation／`match_type` migration；全量 **128 passed**／66.92s；正式 DB **未**動；Commit／Push／PR **待**授權。 |
| 2026-11-26 | **隔離 UAT `fifo_same_day_2236`**：合成九筆；`data/uat/fifo_same_day_2236/`＋`output/uat_fifo_same_day_2236/`；allocated 4000（3600＋400 Pass2）；非 DRAFT；annotation 1000≠400；正式 DB mtime 2026-11-22 14:49:49 未變；判定 **PASS**（`UAT_fifo_same_day_2236.md`）。 |
| 2026-11-26 | **`pr12_cr_fixes_v1` TDD**：PR #12 CR-01～13；RED 5 failed → GREEN annotation／migration／report／E2E／UAT；全量 **145 passed**／57.98s；ruff 通過；正式 DB **未**動；Commit／Push／PR 回覆待授權。 |
| 2026-11-26 | **`pr12_cr_r2_v1` TDD**：PR #12 Round-2；RED 7 failed → GREEN 稅適用／prep 邊界／原始九筆 import E2E／migration／Excel／UAT；全量 **153 passed**／71.67s；隔離 UAT **PASS**；ruff 通過；正式 DB **未**動；Commit／Push／PR 回覆待授權。 |
| 2026-11-26 | **`pr12_cr_r3_v1` TDD**：PR #12 Round-3；inferred／`tw_sec_tax_v3`／E2E permutation／`build_uat_checks` 反向／REQUIRED_AUDIT_KEYS／migration 財務欄／指紋文件；全量 **180 passed**／64.28s；ruff 通過；正式 DB **未**動；Commit／Push／PR 回覆待授權。 |
| 2026-11-26 | **`pr12_cr_r4_v1`（事後驗證）**：PR #12 Round-4；真實 Excel 財務驗證＋檔案層故障注入；Owner canonical 列序；MIXED 分類；全量 **205 passed**／78.18s；ruff 通過；正式 DB **未**動；Commit／Push／PR 回覆待授權。 |
| 2026-11-26 | **`cr10a_finance_verify_v1` TDD**：唯一授權 CR-10A；RED 6 failed（cost／income 同時偏移、qty、單列灌總額、golden 缺鍵）→ GREEN 獨立欄位＋`min_detail_rows`；全量 **211 passed／1 skipped**／83.85s；ruff 通過；正式 DB **未**動；**待複審**；Commit／Push／PR **未**執行。 |
| 2026-11-26 | **`golden_cr_batch2_v1` TDD**：非法鍵 JSON 序列化＋CR-03 WAL／SHM 指紋比＋CR-04 git ls-files；RED 3 failed → GREEN；全量 **248 passed／1 skipped**／63.67s；ruff 通過；正式 DB **未**動；PENDING 維持；Phase 2／Merge／Migration **未**授權。 |
| 2026-11-26 | **`golden_cr_batch3_v1` TDD**：CR-04 returncode、CR-10 列合法性、CR-11 歧義、CR-05 可核對欄；RED 4 failed → GREEN；全量 **252 passed／1 skipped**／64.92s；ruff 通過；正式 DB **未**動；PENDING 外部鍵／多帳戶維持。 |
| 2026-11-26 | **`golden_cr10_close_v1`**：invalid／excluded 分計＋阻擋完整 PASS；Phase 0／1 收斂摘要；全量 **253 passed／1 skipped**／63.96s；ruff 通過；正式 DB **未**動；待 Owner 確認 Phase 2。 |
| 2026-11-26 | **`golden_phase2_expected_c_v1`**：Owner 授權 Phase 2；獨立 C 模組＋合成測；本機 expected_c GOLD-001～004；HTML／玉山 invalid→UNKNOWN；全量 **261 passed／1 skipped**／74.78s；ruff 通過；正式 DB **未**動；真實答案未入 Git；待獨立 Reviewer／CR-10A；Merge／Migration **未**授權。 |
| 2026-11-26 | **`golden_phase2_r2_v1`**：複審修正—唯一 trade_id、負數 TRUNC 朝零、帳戶／幣別分池、來源閘門、逐筆 allocation_lines、GOLD-001-2236；RED 9 failed → GREEN；全量 **269 passed／1 skipped**／81.41s；ruff 通過；正式 DB **未**動；真實答案未入 Git；受測 trunc 負數見 PENDING；Merge／Migration **未**授權。 |
| 2026-11-26 | **`golden_phase3_cr10a_v1`**：Owner 授權 Phase 3；Phase2 FAIL／BLOCKED 非零結束碼；GOLD-TRUNC-NEG 受測朝零；C↔D 比對＋本機 GOLD-001-2236 UAT **PASS**；RED-07 逐筆互抵；CR-10B `uat_exit_code`；GOLD-002／003 PARTIAL、004 C 就緒；全量 **285 passed**／66.31s；ruff 通過；正式 DB **未**動；真實證據未入 Git；Merge／Migration **未**授權。 |
| 2026-11-26 | **`golden_phase3_cr10a_r2_v1`**：複審—allocation_lines↔Trace 逐筆；open_cost 觀測；CR-10B／10C；WAL／SHM；GOLD-004 全年 D **PASS**（HTML bridge）；全量 **288 passed**／65.08s；ruff 通過；正式 DB **未**動；CSV Parser 仍 PENDING；Merge／Migration **未**授權。 |
| 2026-11-26 | **`golden_phase3_wrap_v1`**：合併前收尾—GOLD-004 必要失敗不得 PARTIAL；CR-10C 守恆實際值；CR-10A 重複鍵多重集；CR-10B 觀測非固定 True；Excel 未驗證範圍明示；全量 **299 passed**／74.81s；ruff 通過；GOLD-001／004 UAT **PASS**；正式 DB **未**動；CSV Parser 仍 PENDING；Merge／Migration **未**授權。 |
| 2026-11-26 | **原始 CR 銷帳**：`PR12_ORIGINAL_CR_WRITEOFF.md`；GOLD≠原始 CR；CR-06C 利息／稅落點強化；暫停 Merge Readiness；正式 DB **未**動；待 Reviewer 最終審查。 |
| 2026-11-26 | **`pr12_cr06c_merge_ready_v1`**：CR-06C 第一片段 sequence 對位＋獨立 C／Excel；全量 **299 passed**／61.38s；ruff 通過；隔離 DB integrity／FK 實查；隔離 migration upgrade／downgrade 實查；正式 DB **未**寫入／**未** migrate；Merge **待** Owner 授權。 |
| 2026-11-26 | **`pr12_test_data_audit_v1`**：測試資料來源／誠信稽核表；SOURCE 標籤；非零利息 PENDING skip；全量 **299 passed／1 skipped**／68.28s；ruff 通過；**暫停 Merge**；正式 DB **未**動。 |
