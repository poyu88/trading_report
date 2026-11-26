# UAT：Two-Pass FIFO Same-Day Reconciliation（2236 合成）

> **歷史／驗收證據（Class C）**：隔離合成 UAT；勿當操作手冊。路徑慣例以 `docs/DEVELOPMENT_WORKFLOW.md` §2.8 為準。

| 項目 | 值 |
|---|---|
| 日期 | 2026-11-26 |
| 分支 | `feature/fifo-same-day-reconciliation` |
| 演算法 | `fifo_v3_two_pass_same_day_reconcile` |
| 政策 | `prior_inventory_then_same_day_reconcile` |
| 資料性質 | **合成**九筆 CASH（買＝賣＝4000）；**非**正式帳戶真實對帳單 |
| 正式 DB | 以 size＋mtime＋sha256 指紋比對；UAT **不得**寫入 |

## 1. 隔離路徑（CR-11）

| 類型 | 路徑 |
|---|---|
| SQLite／摘要 | `data/uat/fifo_same_day_2236/run_<stamp>/`（**禁止** `rmtree` 舊 run） |
| 最新指標副本 | `data/uat/fifo_same_day_2236/latest_summary.json` |
| 報表／稽核 | `output/uat_fifo_same_day_2236/` |
| 執行腳本 | `scripts/uat_fifo_same_day_2236.py`（本機；不上傳正式 DB） |

解析後路徑必須落在 `data/uat/...`；否則腳本拒絕執行。

## 2. 產出清單（人工可查）

1. `交易明細_*.xlsx` — 成本／收入／已實現損益（非 DRAFT）
2. `FIFO配對及未配對明細_*.xlsx` — 含 `match_type`
3. `價金費用守恆核對_*.csv` — 數量／價金守恆
4. `*_audit.json` — 含 `day_trade_annotation`（含 CR-12 可追溯欄）
5. `*_exceptions.csv` — 例外清單
6. `run_<stamp>/summary.json` — 含全部步驟後之 `uat_verdict`／`checks`

## 3. Verdict（CR-10：全部步驟後計算）

| 檢查項 | 預期 |
|---|---|
| `migration_match_type_column` | create_all 新 DB 含 `match_type` |
| allocated／STANDARD／Pass2 | 4000／3600／400 |
| unsold／blocking／conservation／integrity | 0／false／true／ok |
| report 存在且非 DRAFT | true |
| annotation 候選 | ≥1 |
| 冪等（舊 run 保留、qty 同） | true |
| H 非干涉（財務鍵 snapshot） | true |
| 正式 DB 指紋未變（size＋mtime＋sha256） | true |
| run_dir 落在 `data/uat` | true |

## 4. Annotation（獨立於配對）

| 欄位 | 說明 |
|---|---|
| `suspected_support_qty` | `min(buy_qty, half_rate_sell_qty)`（非整組 sell） |
| `same_day_reconciled_qty` | Pass2 實際補沖（≠ suspected） |
| `AMBIGUOUS_TAX_EVIDENCE` | 同時近半稅／全稅 → 不標 SUSPECTED |
| 稅規則適用 | 僅 TWD＋CASH＋有效 gross |
| H 非干涉 | 註記前後 allocations 業務鍵全等 |

## 5. 財務合計（合成價；非正式 Owner 真實數字）

由 fixture `Decimal` 獨立重算（見 `tests/test_fifo_same_day_2236_e2e.py`）；不宣稱真實對帳單重現。

## 6. 剩餘風險

- 真實群益／完整帳戶副本 UAT 未在本輪重跑。
- 歷史 v2 run 無法還原 Pass2 `SAME_DAY_RECONCILED`（migration 不猜測）。
- 稅規則表僅涵蓋台股現股 TWD 一般／減半兩檔。
