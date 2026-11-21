# TDD 測試狀態與稽核紀錄

依 `docs/test/TDD.md`、`docs/spec/SPEC.md` §12、以及本檔生命週期追蹤表維護。

> **稽核結論（2026-11-21）**：既有 **34** 項屬**特徵化／回歸安全網**（基準 `cf4e68e`）。`esun_xlsx_v1`、`day_trade_v1`、Cloud Agent **`esun_unsupported_rows_v1`**，以及本機整合後的補充覆蓋，均見 §6.2。
>
> **回歸基準 Commit**：`cf4e68e`。分支基準：`c537d8b`。

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

### 1.8 片段價金 TRUNC＋±1 容許差（本分支最新 REGRESSION）

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
| 是否有 RED／GREEN／REFACTOR 分階段 commit？ | **否**。生命週期追蹤表 §6.2 目前為空。 |
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
| `test_fifo.py` | `test_order_ambiguity_same_day` | 單元 | 回歸 | PASS | FIFO-05 |
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
| 有完整 RED→GREEN→REGRESSION Git 證據 | **4 功能** — `esun_xlsx_v1`、`day_trade_v1`、`esun_unsupported_rows_v1`、`esun_fifo_finance_v1`（見 §6.2） |
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
| AUD-03 同版 FIFO 可重現且舊 run 不覆寫 | 未見獨立斷言 |

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

**記錄欄位最低要求**

- **RED**：會失敗的測試名稱、`pytest` 指令、失敗原因（斷言／例外）、測試 commit SHA（若已入庫）。
- **GREEN**：為讓該測試通過而改的檔案摘要、功能 commit SHA；**禁止**刪除或弱化驗收斷言。
- **REFACTOR**：結構改善說明、commit SHA；完成後必須 `uv run pytest`（全量）且維持既有斷言強度。

---

## 7. 強制流程（自本稽核起）

對任何**新增功能**或 **Bug 修復**，完整政策見 `docs/test/TDD.md`。摘要：

1. **RED**：先寫／擴充分會因「預期行為尚未實現」而失敗的測試；執行並保存失敗輸出。
2. **GREEN**：只做最小實作使該測試通過；不得為綠燈刪減斷言。
3. **REFACTOR**：可改善設計；之後**必須**全量 `uv run pytest`，且不得弱化既有驗收。
4. 於 §6.2 登錄三階段結果與 Git commit。
5. 測試只准使用合成資料與 `tmp_path`／臨時 DB；**禁止**讀寫 `data/trading.db`、真實 `input/` 附件、正式 `output/` 報表，也禁止把真實對帳單提交進 Git。

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
