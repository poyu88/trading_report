# UAT：Two-Pass FIFO Same-Day Reconciliation（2236 合成）

> **歷史／驗收證據（Class C）**：隔離合成 UAT；勿當操作手冊。路徑慣例以 `docs/DEVELOPMENT_WORKFLOW.md` §2.8 為準。

| 項目 | 值 |
|---|---|
| 日期 | 2026-11-26 |
| 分支 | `feature/fifo-same-day-reconciliation` |
| 演算法 | `fifo_v3_two_pass_same_day_reconcile` |
| 政策 | `prior_inventory_then_same_day_reconcile` |
| 資料性質 | **合成**九筆 CASH（買＝賣＝4000）；**非**正式帳戶真實對帳單 |
| 正式 DB | size＋mtime＋sha256（含 `-wal`／`-shm` 若存在）；UAT **不得**寫入 |

## 1. 隔離路徑（CR-11）

| 類型 | 路徑 |
|---|---|
| SQLite／摘要 | `data/uat/fifo_same_day_2236/run_<stamp>/`（**禁止** `rmtree` 舊 run） |
| 最新指標副本 | `data/uat/fifo_same_day_2236/latest_summary.json` |
| 報表／稽核 | `output/uat_fifo_same_day_2236/run_<stamp>/`（每次獨立目錄） |
| 執行腳本 | `scripts/uat_fifo_same_day_2236.py`（本機；不上傳正式 DB） |

解析後路徑必須落在對應 UAT 根之下；否則腳本拒絕執行。

### 正式 DB 指紋限制（CR-11）

- UAT **期間禁止**其他程序寫入正式 `data/trading.db`（含 `-wal`／`-shm`）。
- 指紋比對僅適用「**無並發寫入**」前提；指紋變 → `uat_verdict=FAIL`。
- **不**宣稱涵蓋所有並發、OS 快取、防毒／備份工具等情境。
- Verdict 以 `build_uat_checks`（`scripts/uat_fifo_same_day_2236.py`）組裝之 **全部** `checks` 為準；反向失敗見 `tests/test_uat_fifo_same_day_verdict.py`／檔案層故障注入見 `tests/test_uat_fifo_same_day_file_fault.py`。
- `detail_xlsx_finance_ok` 必須來自 `verify_detail_xlsx_finance`（讀 Excel A–W），**不得**以檔案存在／檔名非 DRAFT 預設 True。
- 必要產出以 audit 內 `fifo_trace_file`／`conservation_file` 實際路徑驗證（`resolve_required_outputs`），不用 glob 關鍵字。

## 2. 產出清單（人工可查）

1. `交易明細_*.xlsx` — 成本／收入／已實現損益（非 DRAFT）
2. `FIFO配對及未配對明細_*.xlsx` — 含 `match_type`
3. `價金費用守恆核對_*.csv` — 數量／價金守恆
4. `*_audit.json` — 含 `day_trade_annotation`（含 CR-12 可追溯欄；`tw_sec_tax_v3`）
5. `*_exceptions.csv` — 例外清單
6. `run_<stamp>/summary.json` — 含全部步驟後之 `uat_verdict`／`checks`
7. `run_<stamp>/migration_probe.db` — 實際 alembic upgrade 探針（≠ fresh schema）

## 3. Verdict（CR-10：全部步驟後計算）

| 檢查項 | 預期 |
|---|---|
| `fresh_schema_has_match_type` | create_all 新 DB 含 `match_type`（與 actual migration 分開） |
| `actual_migration_*` | PREV→seed→HEAD backfill／`cash_standard_ok`／FK／integrity |
| `required_outputs_all` | detail／audit／exceptions／fifo_trace／conservation **全部**存在 |
| allocated／STANDARD／Pass2 | 4000／3600／400 |
| unsold／blocking／conservation／integrity | 0／false／true／ok |
| report／audit／exceptions 存在且非 DRAFT | true |
| **序列化** `audit.json` annotation `status=OK`、suspected=1000、reconciled=400、warnings 空 | true |
| 冪等（舊 run 保留、業務鍵不變、新 run 鍵相等） | true |
| H 非干涉（財務鍵 snapshot） | true |
| 正式 DB 指紋未變（含 WAL／SHM；無並發寫入前提） | true |
| run／out 目錄落在對應 UAT 根 | true |
| `detail_xlsx_finance_ok` | `verify_detail_xlsx_finance` 與 Decimal golden 全等（fail-closed） |
| `annotation_has_warnings_key` | 序列化 annotation **必須**含 `warnings` 鍵 |

必要條件失敗 → `uat_verdict=FAIL`。不得以記憶體 annotation 物件單獨作為最終判定。

## 4. Annotation（獨立於配對）

| 欄位 | 說明 |
|---|---|
| `suspected_support_qty` | `min(buy_qty, half_rate_sell_qty)`（非整組 sell） |
| `same_day_reconciled_qty` | Pass2 實際補沖（≠ suspected） |
| `same_day_sell_trade_ids`／`half_rate_sell_trade_ids` | 區分全部同日賣 vs 半稅候選 |
| `sell_tax_evidences` | 逐筆稅證據＋`source_row_id`＋`instrument_class`／`classification_basis` |
| `AMBIGUOUS_TAX_EVIDENCE` | 同時近半稅／全稅 → 不標 SUSPECTED |
| 稅規則適用 | TWD＋CASH＋有效 gross＋`INFERRED_TW_COMMON_STOCK`（啟發式≠主檔驗證）；減半 ≥2017-04-28；程式核實期限至 2026-12-31（非法令日落）；組級衝突 → `MIXED_INSTRUMENT_EVIDENCE` |
| H 非干涉 | 註記前後 allocations 業務鍵全等 |

## 5. 財務合計（合成價；非正式 Owner 真實數字）

由 fixture `Decimal` 獨立重算（見 `tests/test_fifo_same_day_2236_e2e.py`）。  
原始九筆欄位 Parser／Import 回歸見 `tests/test_fifo_same_day_2236_original_import_e2e.py`（匿名名稱；含同日列序 permutation／Excel／費用守恆）。

## 6. 剩餘風險

- 真實群益／完整帳戶副本 UAT 未在本輪重跑。
- 歷史 v2 run 無法還原 Pass2 `SAME_DAY_RECONCILED`（migration 不猜測；downgrade 為 lossy；正式回滾靠備份）。
- 稅規則表僅涵蓋一般股票最小適用範圍（啟發式推論；非完整稅務引擎／商品主檔）。
- 正式 DB 指紋不涵蓋並發寫入情境（見 §1 CR-11）。
