# 真實交易黃金驗收 — Phase 2 獨立 C 層（R1.0）

> **狀態**：Phase 2 複審通過；Owner 已授權 **Phase 3／CR-10A**。本機 GOLD-001-2236 C↔D **已驗**。Merge／正式 Migration／寫入正式 DB **禁止**。
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
| GOLD-001 | 已獨立核算 | 年度 CSV；逐筆 allocations／allocation_lines；來源 SHA＋illegal gate |
| GOLD-001-2236 | 已獨立核算 | 同年來源篩選 2236 九筆；非硬編碼 Reviewer 數值 |
| GOLD-002 | PARTIAL | `invalid_row_count=UNKNOWN`；缺期初 → unmatched；仍存逐筆（可算範圍） |
| GOLD-003 | PARTIAL | 來源無幣別欄 → 幣別 UNKNOWN，CASH FIFO 不混配；2236 缺買進 |
| GOLD-004 | 已獨立核算 | `trade_id={source_id}:L{line}` 全域唯一；四年度指紋鎖定 |

精確數字與 SHA 見本機 `expected_c/` 與 `evidence/phase02_expected_c_summary.json`。

## 4. 已核算／未核算欄位（語意）

**已由 A＋SPEC 核算（GOLD-001／001-2236／004 完整；002／003 PARTIAL）**

- 原始有效交易筆數、買賣筆數／股數／成交金額／手續費
- 交易稅、利息（來源有明確值時）
- 原始淨收付合計
- FIFO 預期：`STANDARD_FIFO`／`SAME_DAY_RECONCILED` 股數、未配賣出、未售買進
- **逐筆** allocations（trade id／買賣來源／股數／match_type／序）
- **逐筆** allocation_lines（成本／收入／費用落點／價金尾差／conservation）
- 已實現損益（§7；`decimal.ROUND_DOWN`＝朝零，含負數）
- 未平倉股數與成本
- 費用落點政策：`source_values_unsplit`（來源原值；不分攤）
- 來源完整性：SHA256 鎖定＋CSV acceptance gate（失敗不得完整成功）

**尚未能完整核算或維持 UNKNOWN／PENDING**

- HTML／玉山列級 `invalid_row_count`（→ `UNKNOWN` → PARTIAL）
- 玉山無幣別欄（→ 幣別 UNKNOWN；不硬填 TWD）
- 缺核准期初之賣出完整成本／損益（→ PARTIAL／unmatched）
- DAY_TRADE pool（`fifo_scope=CASH_ONLY`）
- 外部 trade id／多帳戶真實樣本／特殊商品等（見 `PENDING_DATA_VALIDATION.md`）
- 報表 A～W 其他代號／全年邊界（見 `PENDING_DATA_VALIDATION.md`）
- GOLD-004 全年 D 端到端（C 已就緒；非 2236 阻擋）

## 5. Phase 3／CR-10A（已接回）

| 項目 | 說明 |
|---|---|
| 比對模組 | `backend/golden/compare_c_d.py`（來源指紋；禁改 C） |
| 管線觀測 | `backend/golden/phase3_pipeline.py` |
| 本機 UAT | `scripts/_golden_phase3_cr10a_uat.py` → `data/uat/golden_cr10a_2236/`＋`runs_d/` |
| 結束碼 | Phase 2：`phase2_exit_code`（FAIL／BLOCKED→非 0）；缺來源鎖定不得 `full_acceptance_ok` |
| TRUNC | 受測 `report_finance.trunc_toward_zero` 正負皆朝零（GOLD-TRUNC-NEG **CLOSED**） |

不得自行 Merge。
