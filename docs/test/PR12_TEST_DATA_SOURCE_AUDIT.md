# PR #12 — 測試資料來源與驗收誠信稽核表（最終複審）

> **性質**：Merge 前稽核（Class C）。**暫停 Merge**；先前有條件通過結論保留。  
> **範圍**：本 PR 測試／fixture／UAT／獨立 C／文件／公開 Git 與 PR Comment；非重開 CR、非大型新功能。  
> **禁止**：新增虛假交易、偽造期初、降低驗收標準、Merge、正式 Migration、寫正式 DB、改寫 Git 歷史／force push。  
> **本回報不貼出完整真實明細。**

## 0. 分類語意

| 代碼 | 意義 |
|---|---|
| `REAL_SOURCE` | 本機真實對帳單／原始 CSV（通常 gitignored） |
| `REAL_DERIVED` | 自真實來源匿名／摘錄／HTML bridge；**仍可能含敏感財務欄** |
| `SYNTHETIC_UNIT` | 合成單元／純函式 |
| `SYNTHETIC_CONTRACT` | 合成契約／管線（常含 price×qty） |
| `FAULT_INJECTION` | 故意損壞產物／受控失敗輸入 |
| `UNVERIFIED_FIXTURE` | 來源不明或未證明 |
| `PENDING_DATA` | 缺可靠資料；不得 PASS |
| `INVALID_EVIDENCE` | 無驗收用途或冒充驗證 |

### 處置類型（本複審強制分列）

| 類型 | 意義 |
|---|---|
| `ANNOTATION_ONLY` | 原有程式／用途已正確，僅補 SOURCE／限制註解 |
| `LOGIC_OR_DOC_FIXED` | 原有表述／用途邊界不清，已實際修正文件或測試說明（非僅貼標） |
| `SYNTHETIC_KEEP_NOT_REAL` | 合成測試保留，**不屬**真實財務證據 |
| `PENDING_REVERIFY` | 待資料後重新驗證 |
| `SENSITIVITY_OWNER_DECIDE` | 敏感／REAL_DERIVED 已公開；**Owner 待決**是否允許保留 |

---

## 1. 真實衍生資料公開風險（複審重點）

### 1.1 事實（已進公開 Git／GitHub）

| 位置 | 是否含真實交易財務欄 | 說明（不貼明細） |
|---|---|---|
| `tests/test_fifo_same_day_2236_original_import_e2e.py` 之 `ORIGINAL_ROWS`（歷史 Commit） | **曾是（歷史）** | 九筆 REAL_DERIVED 財務欄曾嵌入公開追蹤檔；引入自 PR 分支 Commit（含 `ddc7530`／`07d0f31`／`10eab5d` 等）。**工作區已遷至** gitignored `data/golden/private_fixtures/original_rows_2236.json`；公開測試改 skip／私有斷言 |
| 同上檔案（工作區現況） | **否（已遷出）** | 僅載入器＋邏輯；缺檔 → `PRIVATE_FIXTURE_UNAVAILABLE` skip |
| `docs/test/PR12_ORIGINAL_CR_WRITEOFF.md` 等 | **結構／摘要** | 列序敘述已去敏感化；細節僅私有 fixture |
| `tests/fixtures/*.html` | **否（合成）** | 已標合成；非 ORIGINAL_ROWS 特徵價金 |
| 追蹤之 JSON／CSV／Excel | **無** expected_c／真實對帳單入庫 | `git ls-files` 無 `.db`／`input/`／`data/golden/expected_c/*.json` |
| PR #12 Issue Comments（公開） | **是（至少特徵值）** | 至少 1 則含特徵價金常數；另有多則提及 `ORIGINAL_ROWS`／日期結構。inline review comments＝0 |
| 本機未追蹤 `data/`、`_capital_rca_*`、`esun_local_changes.patch` | 可能含真實 | **未**提交；持續禁止入庫 |

**結論**：不得僅依「無 .db／gitignore」宣稱敏感未提交。`ORIGINAL_ROWS` 的 REAL_DERIVED 財務欄**已在公開追蹤 Python 檔與至少一則 PR Comment**。Agent **未**改寫歷史；是否允許繼續保留 → **Owner 待決**（`SENSITIVITY_OWNER_DECIDE`）。

### 1.2 對照：合成軌跡（非同一敏感集合）

`scripts/uat_fifo_same_day_2236.py`／`test_fifo_same_day_2236_e2e.py`／`test_same_day_reconciliation.py` 使用 **price×qty** 合成金額，與 Owner 原始價金不同；屬 `SYNTHETIC_KEEP_NOT_REAL`。

---

## 2. 人工報表與合成驗收（`_write_matching_multi_row_detail_xlsx`）

| 項目 | 內容 |
|---|---|
| 定義處 | `tests/test_uat_fifo_same_day_verdict.py` |
| 行為 | 將合成 golden **均勻拆分**到多列（殘差末列） |
| 呼叫端 | 僅本檔：`test_verify_detail_xlsx_finance_ok_on_matching_totals`（比較器 ok）及多個 RED／FAULT 竄改基底；**無** UAT 主流程／FIFO E2E／GOLD 真實路徑呼叫 |
| 合法用途 | `verify_detail_xlsx_finance` **比較器**單元／契約／故障注入 |
| 非法用途（禁止） | 當作 FIFO／TRUNC 片段正確、或真實財務正向驗收 |
| 複審前問題 | 稽核表寫「未作為正向證據」過於籠統；`ok_on_matching_totals` 確為比較器**正向**路徑，易被誤讀為 FIFO 證據 |
| 複審修正 | **LOGIC_OR_DOC_FIXED**：函式與 ok 測試 Docstring 改為明示「僅比較器；均分≠FIFO；非真實財務」 |

`_write_minimal_detail_xlsx`：單列灌總額，**僅反例**（FAULT）→ `SYNTHETIC_KEEP_NOT_REAL`。

真實／管線 FIFO 財務正向證據應來自：REAL_DERIVED original import E2E、隔離合成 UAT（流程契約）、或本機 REAL_SOURCE GOLD UAT（gitignored）— **不是**人工均分 xlsx。

---

## 3. 處置分列總表（勿一律「未發現問題」）

### 3.1 ANNOTATION_ONLY（原已正確，僅補標）

| 項目 | 說明 |
|---|---|
| 多數 `SOURCE:` 模組標籤 | annotation／same_day／migration／golden unit／fixtures／UAT 合成腳本標籤 |
| `fifo_fee.html` 合成註解 | 補齊 |
| UAT `expectations` 註解 | 判定仍以 checks／verify 為準（原邏輯已如此） |

### 3.2 LOGIC_OR_DOC_FIXED（本複審或前輪有實質邊界修正）

| 項目 | 說明 |
|---|---|
| CR-06C Trace 第一片段 sequence 對位 | **前輪**強化斷言（非僅註解） |
| `_write_matching_multi_row_detail_xlsx`＋ok 測試 Docstring | **本複審**釐清用途，修正「冒充 FIFO／真實財務」誤讀風險 |
| 稽核表 §1／§2／§3 | **本複審**改寫：承認 REAL_DERIVED 已公開；人工均分用途收緊 |
| ORIGINAL_ROWS 模組頭 | **本複審**標敏感風險＋Owner 待決；Docstring 減少特徵價金複述 |

### 3.3 SYNTHETIC_KEEP_NOT_REAL

| 項目 | 說明 |
|---|---|
| UAT／E2E／Pass2 `TRADES`（price×qty） | 演算法／隔離契約；非真實價金 |
| annotation／golden 合成單元 | 契約有效；非完整真實稅務／帳戶驗收 |
| 人工均分／單列灌總額 helper | 僅比較器／FAULT |
| `finance_ok=True` 於 verdict 單元 | 受控輸入測判定邏輯 |

### 3.4 PENDING_REVERIFY

| 項目 | 說明 |
|---|---|
| CR-06C 非零利息 | `test_cr06c_nonzero_interest_first_fragment_pending_data` **skipped** |
| GOLD-CSV-PARSER | HTML bridge ≠ 原始 CSV Parser |
| 真實帳戶全集財務差異 | DEFERRED／PENDING_DATA |
| GOLD-CR-02／05 等 | 見 `PENDING_DATA_VALIDATION.md` |

### 3.5 SENSITIVITY_OWNER_DECIDE

| 項目 | 說明 |
|---|---|
| `ORIGINAL_ROWS` 留在公開 Git | **Owner 已決：遷出**。工作區已遷私有 fixture；**歷史仍污染**至 feature branch（待隔離 filter-repo／遠端授權） |
| PR Comment 中特徵價金 | 已公開；清理清單已備；本輪不批次刪遠端留言 |

---

## 4. 十項檢查（複審後誠實表述）

| # | 檢查項 | 複審結論 |
|---|---|---|
| 1 | 未標記交易 | 合成已標；REAL_DERIVED 已標但**有公開風險** |
| 2 | 人工均分／灌總額 | 均分 helper **僅比較器／FAULT**（本複審文件收緊）；灌總額為反例 |
| 3 | 反推 Expected | 未發現 C／UAT golden 自 Excel 反推 |
| 4 | Expected→Actual | 未發現 |
| 5 | 固定 True 冒充 | 未發現 UAT 主流程固定 True；單元受控 True 已標 |
| 6 | 缺資料填 0／成功 | 合成 interest=0 已標；非零利息 PENDING skip |
| 7 | 為過測改 Expected | 未發現本輪為此削弱斷言 |
| 8 | 未接入主流程 | 主要 verify／checks 已接入 |
| 9 | 未執行稱 PASS | 合成 UAT／GOLD bridge 範圍已文件化；不得越界 |
| 10 | 敏感進公開 Git | **有**：REAL_DERIVED 九筆財務欄在追蹤測試檔＋PR Comment 特徵值；無完整 DB／CSV 入庫 |

---

## 5. Owner 決策與後續（2026-11-26 遷出輪）

1. **已決**：不允許 REAL_DERIVED 財務欄繼續留在公開 Git；工作區已遷至 gitignored private fixture。  
2. **進行中**：敏感留言清理清單已盤點；本輪不批次刪遠端。  
3. **進行中**：隔離 git-filter-repo 演練（不 force push／不改遠端）。  
4. 人工均分 xlsx **僅**比較器用途之文件收緊維持。  
5. Merge 仍暫停。

---

## 6. 本輪執行範圍

- 更新本稽核表；收緊人工均分／ORIGINAL_ROWS 敏感說明。  
- **未**重跑無關大型 GOLD／真實帳戶 UAT（依 Owner：僅文件／註解時不必）。  
- 相關單元測試可抽樣確認；全量 pytest 若僅註解變更可視 CI／需要補跑。  
- **未** Merge／**未**正式 Migration／**未**寫正式 DB。

---

## 7. 變更紀錄

| 日期 | 說明 |
|---|---|
| 2026-11-26 | 初版：SOURCE 標籤；PENDING skip；暫停 Merge |
| 2026-11-26 | **最終複審**：REAL_DERIVED 公開風險事實；人工均分用途收緊；處置分列 ANNOTATION_ONLY／FIXED／SYNTHETIC／PENDING／SENSITIVITY；Owner 待決 |
