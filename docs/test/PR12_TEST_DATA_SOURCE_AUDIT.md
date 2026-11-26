# PR #12 — 測試資料來源與驗收誠信稽核表

> **性質**：Merge 前稽核（Class C）。**暫停 Merge**；先前有條件通過結論保留。  
> **範圍**：本 PR 測試／fixture／UAT／獨立 C／文件；非重開全部 CR、非大型新功能。  
> **禁止**：新增虛假交易、偽造期初、降低驗收標準、Merge、正式 Migration、寫正式 DB、改寫 Git 歷史。

## 0. 分類語意

| 代碼 | 意義 |
|---|---|
| `REAL_SOURCE` | 本機真實對帳單／原始 CSV（通常 gitignored） |
| `REAL_DERIVED` | 自真實來源匿名／摘錄／HTML bridge；保留原始價金等財務欄 |
| `SYNTHETIC_UNIT` | 合成單元／純函式 |
| `SYNTHETIC_CONTRACT` | 合成契約／管線（常含 price×qty） |
| `FAULT_INJECTION` | 故意損壞產物／受控失敗輸入 |
| `UNVERIFIED_FIXTURE` | 來源不明或未證明 |
| `PENDING_DATA` | 缺可靠資料；不得 PASS |
| `INVALID_EVIDENCE` | 無驗收用途或冒充驗證 |

---

## 1. 十項重點檢查結論

| # | 檢查項 | 結論 |
|---|---|---|
| 1 | Agent 任意建立未標記交易 | **未發現未標記項**；本輪補 SOURCE 標籤。合成軌跡與 Owner REAL_DERIVED 已分開 |
| 2 | 人工平均拆分／灌總額報表 | **未作為正向證據**；`test_uat_fifo_same_day_verdict` 有單列灌總額 **反例**（FAULT） |
| 3 | 從受測輸出反推 Expected | **未發現**；C 禁依賴 Projector；UAT golden 自 TRADES／C 核算；`observe_open_cost_*` 僅觀測 Actual |
| 4 | Expected 填入 Actual | **未發現** |
| 5 | 固定 True／成功字串冒充 | **未發現冒充**；`finance_ok=True` 僅出現在 verdict **單元**受控輸入；UAT `detail_xlsx_finance_ok` 來自 `verify_*`；fault 觀測非固定 True |
| 6 | 缺資料填 0／成功 | **已知限制已標**；合成 UAT interest=0 屬 SYNTHETIC；CR-06C 非零利息 → PENDING skip |
| 7 | 為過測改 Expected | **未發現**本輪為配合失敗而改寫 golden |
| 8 | 驗收函式未接入主流程 | **主要函式已接入**（`verify_detail_xlsx_finance`／`build_uat_checks`／`verify_audit_artifacts_content`／`decide_gold004_verdict`） |
| 9 | 未執行卻宣稱 PASS | **文件已區分**合成 UAT PASS vs REAL／PENDING；GOLD-004 HTML bridge ≠ CSV Parser |
| 10 | 真實明細／敏感進公開 Git | **Git 追蹤無** `.db`／`.env`／`input/`／expected_c JSON；fixtures 為合成 HTML |

**敏感資料 Git 歷史**：目前追蹤檔未見真實帳戶明細。本機未追蹤之 `esun_local_changes.patch`／`scripts/_capital_rca_*`／`data/` **不得**提交。若未來發現已入歷史，僅回報範圍，**禁止** force push／改寫歷史。

---

## 2. 逐項稽核

| 檔案／函式 | 分類 | 用途 | 獨立驗收價值 | 問題 | 決策 | 待資料條件 |
|---|---|---|---|---|---|---|
| `tests/test_fifo_same_day_2236_original_import_e2e.py`／`ORIGINAL_ROWS` | REAL_DERIVED | Owner 九筆欄位→管線；CR-06A/B/C | 有（原始價金／列序／費用第一片段） | 利息皆 0 | **保留＋標籤**；新增 PENDING skip | 非零利息真實樣本 |
| 同上／`test_cr06c_nonzero_interest_*` | PENDING_DATA | 占位 | 未來有 | 無資料 | **skip（明確 reason）** | 真實非零利息列 |
| `tests/test_fifo_same_day_2236_e2e.py`／`TRADES` | SYNTHETIC_CONTRACT | RCA 合成 E2E | 部分（演算法契約） | price×qty≠券商價金 | **保留**；禁止當真實財務 | — |
| `scripts/uat_fifo_same_day_2236.py`／`TRADES`＋`verify_*` | SYNTHETIC_CONTRACT | 隔離合成 UAT | 有（流程／verdict／隔離） | 非真實價金；interest=0 | **保留**；expectations 註明非判定來源 | 真實帳戶副本另列 PENDING |
| `tests/test_uat_fifo_same_day_verdict.py` | SYNTHETIC_CONTRACT＋FAULT | fail-closed／灌總額反例 | 有 | 無 | **保留** | — |
| `tests/test_uat_fifo_same_day_file_fault.py` | FAULT_INJECTION | 檔案層故障 | 有（範圍內） | 未跑 migration／冪等／H | **保留**；已排除未宣稱 checks | — |
| `tests/test_day_trade_annotation.py` | SYNTHETIC_UNIT | 稅／支持股數／例外 | 有（契約） | 非完整稅引擎 | **保留** | 特殊商品真實樣本分列 |
| `tests/test_annotation_report_noninterfere.py` | SYNTHETIC＋FAULT | ON/OFF／fault | 有 | 無 | **保留** | — |
| `tests/test_same_day_reconciliation.py` | SYNTHETIC_UNIT／CONTRACT | Pass2 契約 | 有 | 無 | **保留** | — |
| `tests/test_match_type_migration.py` | SYNTHETIC_CONTRACT | migration 探針 | 有 | lossy downgrade | **保留** | — |
| `tests/test_golden_*.py`（expected_c／compare／phase*／cr_fixes） | SYNTHETIC_UNIT／CONTRACT／FAULT | C 層與比對契約 | 有 | 真實 C JSON 不上 Git | **保留** | 本機 REAL 見 UAT 腳本 |
| `tests/test_report_finance_trunc_neg.py` | SYNTHETIC_UNIT | trunc 朝零 | 有 | 無 | **保留** | — |
| `tests/test_decimal_text_normalize.py` | SYNTHETIC_UNIT | Decimal 正規化 | 有 | 無 | **保留** | — |
| `tests/fixtures/statement_sample.html` | SYNTHETIC_UNIT | Parser 結構 | 有 | 已標合成 | **保留** | — |
| `tests/fixtures/fifo_fee.html` | SYNTHETIC_UNIT | 費用落點 | 有 | 本輪補 SOURCE 註解 | **保留** | — |
| `scripts/_golden_phase3_cr10a_uat.py` | REAL_SOURCE→DERIVED | GOLD-001 隔離 UAT | 有（本機） | 證據 gitignored | **保留**；缺檔不得 PASS | — |
| `scripts/_golden_phase3_gold004_uat.py` | REAL_SOURCE→DERIVED | GOLD-004 | 部分 | HTML bridge；CSV Parser PENDING | **保留** | capital_csv profile |
| `backend/golden/expected_c.py` | （演算法；答案來源外部） | 獨立 C | 有 | 禁 import 受測 FIFO | **保留** | — |
| `backend/golden/compare_c_d.py`／`phase3_pipeline.py` | n/a | C↔D／觀測 | 有 | open_cost 觀測≠改 C | **保留** | — |
| `docs/test/UAT_fifo_same_day_2236.md` | 文件 | 合成 UAT 紀錄 | — | 已標合成 | **保留** | — |
| `docs/test/PR12_ORIGINAL_CR_WRITEOFF.md` | 文件 | 原始 CR 銷帳 | — | 與 GOLD 分列 | **保留** | 見 PENDING |
| 未追蹤 `scripts/_capital_rca_*`／`esun_local_changes.patch` | 本機／勿入 Git | RCA | — | 可能含敏感 | **不提交** | — |

**本輪未發現需 REMOVE 的 INVALID_EVIDENCE。** 未為維持通過數而停用有效測試。

---

## 3. 本輪修正摘要

1. 關鍵測試／UAT／fixture／golden 腳本補 `SOURCE:` 標籤與限制說明。  
2. 新增 `test_cr06c_nonzero_interest_first_fragment_pending_data`（`pytest.skip`＋PENDING reason），避免未完成項從報告消失。  
3. UAT `expectations` 註明僅供人工對照，判定以 `checks`／`finance_verify` 為準。  
4. `fifo_fee.html` 補合成來源註解。

---

## 4. 測試結果（實際）

| 項目 | 結果 |
|---|---|
| `uv run pytest -q` | **299 passed，1 skipped，0 failed，0 xfail**／68.28s |
| `uv run ruff check .` | All checks passed |
| 相對先前 299 passed | passed **不變**；**skipped +1**＝`test_cr06c_nonzero_interest_first_fragment_pending_data`（PENDING_DATA 占位，非削弱斷言） |
| 正式 DB | **未**寫入／**未** migrate |
| 品質指標 | 不以通過數為唯一標準；見本表分類與十項檢查 |

---

## 5. 變更紀錄

| 日期 | 說明 |
|---|---|
| 2026-11-26 | 初版：Merge 前測試資料來源／誠信稽核；SOURCE 標籤；PENDING skip；暫停 Merge |
