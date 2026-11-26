# UAT：Two-Pass FIFO Same-Day Reconciliation（2236 合成）

> **歷史／驗收證據（Class C）**：隔離合成 UAT；勿當操作手冊。路徑慣例以 `docs/DEVELOPMENT_WORKFLOW.md` §2.8 為準。

| 項目 | 值 |
|---|---|
| 日期 | 2026-11-26 |
| 分支 | `feature/fifo-same-day-reconciliation` |
| 演算法 | `fifo_v3_two_pass_same_day_reconcile` |
| 政策 | `prior_inventory_then_same_day_reconcile` |
| 資料性質 | **合成**九筆 CASH（買＝賣＝4000）；**非**正式帳戶真實對帳單 |
| 正式 DB | `data/trading.db` mtime **2026-11-22 14:49:49**（UAT 前後不變） |

## 1. 隔離路徑

| 類型 | 路徑 |
|---|---|
| SQLite | `data/uat/fifo_same_day_2236/uat.db` |
| 彙總 JSON | `data/uat/fifo_same_day_2236/summary.json` |
| 報表／稽核 | `output/uat_fifo_same_day_2236/` |
| 執行腳本 | `scripts/uat_fifo_same_day_2236.py`（本機；不上傳正式 DB） |

## 2. 產出清單（人工可查）

時間戳：`2026-11-26_12-28-19`（**非 DRAFT**，因無 blocking）

1. `交易明細_*.xlsx` — 成本／收入／已實現損益
2. `FIFO配對及未配對明細_*.xlsx` — 含 `match_type`
3. `價金費用守恆核對_*.csv` — 數量／價金守恆
4. `*_audit.json` — 含 `day_trade_annotation`
5. `*_exceptions.csv` — 例外清單（本次空）

## 3. 配對結果

| 指標 | 預期 | 實際 |
|---|---:|---:|
| allocated_qty | 4000 | 4000 |
| STANDARD_FIFO | 3600 | 3600 |
| SAME_DAY_RECONCILED | 400 | 400 |
| unsold_qty | 0 | 0 |
| blocking | false | false |
| issue_codes | （空） | （空） |
| conservation_ok | true | true |
| integrity_check | ok | ok |
| 明細是否 DRAFT | 否 | 否 |

冪等：第二次 `match` 新增獨立 run；舊 run 保留；allocated_qty 相同。

## 4. Annotation（獨立於配對）

| 欄位 | 值 | 說明 |
|---|---:|---|
| suspected_day_trade_qty | 1000 | 08-28 同日買賣支持上限（稅減半證據） |
| same_day_reconciled_qty | 400 | Pass2 實際補沖（≠ suspected） |
| tax_evidence | HALF_RATE | 輔助證據；不驅動配對 |
| H 非干涉 | true | 註記不改 allocations |

## 5. 財務合計（合成價；非正式 Owner §13 真實數字）

| 項目 | 值 |
|---|---:|
| buy_gross | 419000 |
| sell_gross | 449021 |
| commission_total | 225 |
| tax_total | 1178 |

> Owner 計畫 §13 之 415500／411710／767／1088／−5645 屬真實對帳單數量級參考；本次 UAT 刻意使用合成單價，僅驗證配對／守恆／報表產線。

## 6. 結論

| 檢查項 | 結果 |
|---|---|
| FIFO 配對（含 Pass2） | **PASS** |
| 剩餘庫存 | **PASS**（0） |
| 成本／收入／損益報表 | **PASS**（已產出非 DRAFT） |
| 數量守恆 | **PASS** |
| 例外清單 | **PASS**（無 blocking） |
| 正式 DB 未觸碰 | **PASS** |
| Annotation 獨立性 | **PASS** |

**UAT 判定：PASS（合成隔離）** — 人工抽查上述 xlsx／audit／conservation 後即可作為合併前業務證據；**不等於** GitHub CI 或正式帳戶全量重跑授權。
