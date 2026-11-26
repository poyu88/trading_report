# RCA：Two-Pass FIFO Same-Day Reconciliation（2236）

> Gate 1 根因＋Gate 2 核准後實作摘要。契約以 PRD／SPEC 為準。

## 根因

| 層 | 判定 |
|---|---|
| Import／去重／分類 | 非缺陷 |
| Matching（v2 政策） | **根因**：CASH 刻意禁止同日 BUY 解當日 SELL，無補沖銷 → 同日同時出現未配賣出與未售買進 |

PR7 UAT 將 2236 未配 400 標為「資料導入問題／DEFERRED」。對完整九筆 CASH 案例（買＝賣＝4000），屬 **Matching 契約缺口**，非漏匯入。

## 修復（v3）

1. **Pass 1**：維持開盤前庫存優先；不當日買穿插解套；`STANDARD_FIFO`。
2. **Pass 2**：僅以**同日**尚未消耗之 CASH BUY lot 補沖當日未配 SELL；`SAME_DAY_RECONCILED`；禁止跨日。
3. **Annotation（Layer 3）**：唯讀稽核註記；ON／OFF 不得改寫財務。
4. Schema：`fifo_allocations.match_type`（Alembic `b2c3d4e5f6a7`）。
5. 版本：`fifo_v3_two_pass_same_day_reconcile`／`prior_inventory_then_same_day_reconcile`。

## 驗證

- 合成 2236：Pass1＝3600、Pass2＝400、期末庫存 0、未配 0。
- 全量 `uv run pytest -q`：**128 passed**（2026-11-26）。
- 正式 `data/trading.db`：**未** apply／migrate／寫入。
