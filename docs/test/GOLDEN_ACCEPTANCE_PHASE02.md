# 真實交易黃金驗收 — Phase 2 獨立 C 層（R1.0）

> **狀態**：Owner 已授權 Phase 2；獨立 C 本機產出。**CR-10A 仍未結案**。Merge／正式 Migration／寫入正式 DB **禁止**。
> **本文件**：非敏感技術規範。**禁止**貼入真實交易明細、帳戶號碼、完整財務答案數字。

## 1. 目標

建立 **C 層**：僅由 **A 原始來源＋正式 SPEC** 以 `Decimal` 獨立推導之財務標準答案。

| 禁止 | 說明 |
|---|---|
| 受測 FIFO | 不得呼叫／匯入 `fifo_matcher`／`allocation_service` 反推答案 |
| Report Projector／新版 Excel | 不得以受測輸出反推 C |
| 虛假交易／偽造期初 | 缺資料 → `PENDING_DATA`／`UNKNOWN`／`PARTIAL`，不得補造 |
| 未知當成功 | HTML／玉山 `invalid_row_count` → `UNKNOWN` |

舊版報表（B）僅可作差異對照，不得當正向答案。

## 2. 公開程式與本機產物

| 路徑 | 進公開 Git？ | 說明 |
|---|---|---|
| `backend/golden/expected_c.py` | 是 | 獨立彙總／CASH Two-Pass／§7 損益核算 |
| `scripts/_golden_phase2_expected_c.py` | 是 | 本機唯讀產出腳本（讀 A；不寫正式 DB） |
| `tests/test_golden_expected_c.py` | 是 | 合成資料契約測 |
| `data/golden/expected_c/*.json` | **否** | 真實財務答案（gitignored） |
| `data/golden/evidence/phase02_*.json` | **否** | 本機摘要 |

## 3. 案例狀態（無明細數字）

| case | C 層 | 備註 |
|---|---|---|
| GOLD-001 | 已獨立核算 | 年度 CSV；含 FIFO／同日補沖／已實現／未平倉；費用來源落點彙總 |
| GOLD-002 | 已獨立核算（部分） | 來源彙總＋FIFO；缺期初 → unmatched／PARTIAL；`invalid_row_count=UNKNOWN` |
| GOLD-003 | 已獨立核算（部分） | 同上；2236 缺買進明確標記；不得混配／自造期初 |
| GOLD-004 | 已獨立核算 | 四年度 CSV 串接彙總＋FIFO；多檔指紋見 sources |

精確數字與 SHA 見本機 `expected_c/` 與 `evidence/phase02_expected_c_summary.json`。

## 4. 已核算／未核算欄位（語意）

**已由 A＋SPEC 核算（GOLD-001 完整；002／003 視期初可能 PARTIAL）**

- 原始有效交易筆數、買賣筆數／股數／成交金額／手續費
- 交易稅、利息（來源有明確值時）
- 原始淨收付合計
- FIFO 預期：`STANDARD_FIFO`／`SAME_DAY_RECONCILED` 股數、未配賣出、未售買進
- 已實現損益（§7 TRUNC＋費用第一片段）
- 未平倉股數與成本
- 費用落點政策：`source_values_unsplit`（來源原值；不分攤）

**尚未能完整核算或維持 UNKNOWN／PENDING**

- HTML／玉山列級 `invalid_row_count`（→ `UNKNOWN`）
- 缺核准期初之賣出完整成本／損益（→ PARTIAL／unmatched）
- 外部 trade id／多帳戶真實樣本／特殊商品等（見 `PENDING_DATA_VALIDATION.md`）
- 報表 A～W 逐欄與 CR-10A 財務驗證器綁定（待獨立 Reviewer／CR-10A）

## 5. 下一步

Phase 2 完成後等待獨立 Reviewer，準備接回 **CR-10A** 財務驗證。不得自行 Merge。
