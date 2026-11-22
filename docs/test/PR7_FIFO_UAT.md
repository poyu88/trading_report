# PR #7 FIFO Code Review 修正 — 真實副本 UAT 摘要

日期：2026-11-22  
分支：`feat/cash-prior-inventory-fifo`  
基準碼：worktree `@77f3ed7`  
候選碼：工作樹（CR-01～CR-04 修正後）  
正式來源：`data/trading.db`（**唯讀**；未 match／migrate／VACUUM）

> 本檔僅彙總數字與分類結論；不含完整交易清單、帳戶個資或 DB／xlsx 附件。

---

## 1. 來源鎖定

| 項目 | 值 |
|---|---|
| 帳戶標籤 | `main`（本庫唯一） |
| trades | 504（BUY 233／SELL 271） |
| opening_lots | 0 |
| 既有 run | `fifo_v1` ×1；blocking `ORDER_AMBIGUITY` ×13 |
| integrity_check | ok |
| 來源 mtime（UAT 前後） | 2026-11-22 14:49:49（未變） |

## 2. 快照方法

- Backup API：`file:…?mode=ro` + `Connection.backup()` → `data/uat/pr7_fifo/source_snapshot.db`
- 再複製：`baseline_before.db`、`candidate_after.db`（非同 inode／硬連結）
- 快照 trades／raw_rows／opening_lots 內容雜湊與來源一致；integrity=ok

## 3. 執行方式

| 側 | 碼 | DB 副本 | 指令 |
|---|---|---|---|
| 基準 | worktree `77f3ed7` | `baseline_before.db` | `match fifo` → `audit`（`--db` 於子命令後） |
| 候選 | 修正後工作樹 | `candidate_after.db` | 同上；並再 `match` 一次驗證冪等 |

## 4. 配對彙總對照

| 指標 | 基準（77f3ed7） | 候選（CR 修正） |
|---|---|---|
| allocations（筆） | 397 | 397 |
| allocated_qty | 71232 | 71232 |
| unsold_lots | 8 | 8 |
| blocking | true | true |
| 新 run 阻擋碼 | `INSUFFICIENT_PRIOR_BUYS` ×1（2236／2024-08-28／未配 400） | 同左 |
| conservation_ok | true | true |
| commission_total | 17147 | 17147 |
| tax_total | 27818 | 27818 |
| 新 run `algorithm_version` | `fifo_v1` | `fifo_v2_cash_prior_inventory` |
| 新 run fingerprint | `6718726a…` | `75f8847b…`（含 source_order／帳戶／政策標記） |

舊 `ORDER_AMBIGUITY`×13 僅存在於來源既有 run；重跑後**不再**產生該碼。

## 5. 事實表不變

| 檢查 | 結果 |
|---|---|
| snap vs base／cand：`trades`／`raw_rows`／`opening_lots` 筆數＋內容雜湊 | 一致 |
| 兩副本 `integrity_check` | ok |
| 候選重跑 | allocations／issue 業務結果相同；新增獨立 run 列；舊 run 未覆寫 |

## 6. 1589 驗收（彙總）

交易日形態（股數）：

- 2023-02-03 BUY 1000＠68.1
- 2023-03-20 SELL 1000＠69.8 ＋ BUY 1000＠72.8（同日 CASH、無 time／seq）
- 後續 03-24／03-27 買、03-28 三筆賣（略）

配對結果（基準＝候選）：

| SELL 日 | 配對來源買日／價 | 股數 |
|---|---|---|
| 2023-03-20＠69.8 | **2023-02-03＠68.1**（開盤前庫存） | 1000 |
| 2023-03-28＠79.8 | 2023-03-20＠72.8（同日買翌日後才用） | 1000 |
| 2023-03-28＠80.3 | 2023-03-24＠76.3 | 1000 |
| 2023-03-28＠79.3 | 2023-03-27＠81.7 | 1000 |

結論：同日 SELL 未沖當日 BUY＠72.8；無 `ORDER_AMBIGUITY`；成本路徑與庫存優先政策一致。

## 7. 差異分類

| 類 | 說明 |
|---|---|
| **A 政策** | 舊 run 的 `ORDER_AMBIGUITY`×13 → 新政策重跑改為合理 `INSUFFICIENT_PRIOR_BUYS`×1（2236 缺庫存 400）；1589 同日改沖舊庫存 |
| **B 稽核修正** | CR-01 版本字串／政策寫入 run；CR-02 守恆含 opening（本庫 opening=0，conservation 仍 ok）；CR-03 fingerprint 欄位擴充導致雜湊變更 |
| **C 資料品質** | 2236／2024-08-28 未配 400：缺更早期初或買進事實，需人工補 lot／資料，非演算法短路 |
| **D 異常阻擋** | **無**無法解釋之財務差異 |

## 8. 自動化回歸（本機）

| 項目 | 結果 |
|---|---|
| RED（CR 測試先行） | `tests/test_fifo_cr_fixes.py`＋`test_fifo_sqlite_integration.py`：**9 failed／5 passed**（版本／守恆／fingerprint 缺口） |
| GREEN 後同檔 | **14 passed** |
| `uv run pytest tests/test_fifo.py -q` | **17 passed** |
| `uv run pytest -q` | **120 passed**／65.16s |

## 9. 安全

- 未寫入 `data/trading.db`
- UAT DB／log／json 僅在 `data/uat/pr7_fifo/`（gitignore）
- 本摘要可提交；真實明細不上傳

## 10. 剩餘風險

- 同日多 SELL 缺可信序時，`source_order` 僅穩定鍵；逐筆成本路徑可能需人工判斷（標於 A／C，不重啟 ORDER_AMBIGUITY）
- 2236 未配對 400 待補期初／事實後再 UAT
- 本機 pytest ≠ GitHub CI ≠ 人工終局簽核

## 11. Code Review（自我／獨立角度）

對照 CR-01～04 與 UAT：**PASS WITH NOTES**

- NOTES：CLI 全域前置 `--db` 會被子命令 parents 預設覆寫為 `None`（既有問題）；UAT／文件已改為子命令後傳遞。建議後續修 argparse，但不阻斷本 PR。

## 12. 結論

**APPROVE**（就 CR 修正與副本 UAT 而言）

不 Merge、不 Force Push；待 GitHub CI 與使用者授權後再合併。
