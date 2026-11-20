# TDD 測試狀態與稽核紀錄

依 `docs/test/TDD.md`、`docs/spec/SPEC.md` §12、以及本檔生命週期追蹤表維護。

> **稽核結論（2026-11-20）**：目前 **34 個測試全部通過**，屬有效的**特徵化／回歸安全網**；**沒有**可驗證的「測試先失敗 → 最小實作 → 重構」TDD 生命週期證據。不得將事後補測且直接綠燈的案例宣稱為 RED。
>
> **回歸基準 Commit**：`cf4e68e`（`add：建立現有功能回歸測試基準版本（非 TDD 完成）`）。將程式碼、測試與 `tdd-rule` 首次入庫的 commit 僅作為**現有功能回歸測試基準版本**，**不得**標記或解讀為「已完成 TDD」。真正的 TDD 自下一筆新需求起，依 `docs/test/TDD.md`（`.cursor/rules/tdd-rule.mdc` 強制引用）執行 RED→GREEN→REFACTOR→REGRESSION，並記入 §6.2。

---

## 1. 實際執行狀態（非文件自述）

| 項目 | 結果 |
|---|---|
| 指令 | `uv run pytest -v --tb=line` |
| 收集數 | 34 |
| 結果 | **34 passed**（0 failed / 0 skipped） |
| 耗時 | 約 121s（2026-11-20 約 19:34–19:36 UTC+8） |
| 工作目錄 | `C:\Users\billh\python_test\trading_report` |
| 正式 DB | `data/trading.db` 在本次 pytest 期間**未被改寫**（檔案 mtime 仍為 2026-11-20 18:51:21；測試僅用 `tmp_path`） |

同一輪另以 `uv run pytest --collect-only -q` 確認清單與下方分類表一致。

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
| 有完整 RED→GREEN→REFACTOR＋Git 證據 | **0** |
| 僅回歸／特徵化 | **34** |

---

## 5. SPEC §12 覆蓋缺口（誠實對照）

已有測試覆蓋的重點：ING-01/02、NORM-01、DB-01/02/03（基本）、FIFO-01～06、FEE-01/02、REP-01～04/07、AUD-01/02。

仍弱或未見獨立自動化案例（不虛構通過）：

| SPEC ID | 狀態 |
|---|---|
| ING-03 CP950／未知編碼 | 僅 UTF-8 偵測；CP950／錯誤編碼未完整覆蓋 |
| ING-04 真 XLS／XLSX | 未見獨立測試 |
| NORM-02 千分位／禁 float | 未見獨立斷言 |
| NORM-03 未支援類型／壞日期 | 未見獨立斷言 |
| FEE-03 gross 尾差守恆 | 未見獨立斷言 |
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

### 6.2 未來条目範本（下一筆新需求從這裡填）

| 功能 ID | 說明 | RED（日期／指令／失敗摘要／commit） | GREEN（日期／最小變更／commit） | REFACTOR（日期／變更摘要／commit） | REFACTOR 後全量 pytest | 備註 |
|---|---|---|---|---|---|---|
| _(尚無)_ | — | — | — | — | — | 下一需求起強制使用 |

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

既有 34 項繼續作為回歸門檻；它們的存在**不構成**歷史 TDD 完成證明。回歸基準 Commit：`cf4e68e`。

---

## 8. 執行方式

```powershell
cd C:\Users\billh\python_test\trading_report
uv sync
uv run pytest tests/test_tdd_cli_contract.py -q -x --tb=short
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
