# 根因報告：群益 FIFO／財務正確性稽核（Phase 1 只讀）

> **歷史快照（Class C）**：記錄當時只讀稽核結論。現行財務契約以 `docs/spec/SPEC.md` 為準；勿當操作手冊。

日期：2026-11-21  
分支：`feature/capital-fifo-finance-audit`（HEAD `27b411d`，與 master 同步）  
依據：

- 來源：`input/群益.xls`（未修改）
- 隔離 DB：`data/uat_capital.db`
- 新 UAT 輸出：`output/uat_capital/交易明細_DRAFT_2026-11-21_12-50-34*`、`FIFO配對及未配對明細_2026-11-21_12-50-34.xlsx`、`價金費用守恆核對_2026-11-21_12-50-34.csv`
- 舊群益 DRAFT（對照、未覆寫）：`output/交易明細_DRAFT_2026-11-20_18-51-21*`

範圍：**只讀正式證據**；新建隔離 UAT 產物與本 RCA。  
**未改**正式 `data/trading.db`、來源 Excel、舊 DRAFT、`backend/` 正式程式；**未** Commit／Push／Merge。

測試基準：`uv run pytest -q` → **90 passed**（约 62s）。

管線：`statement_html_v1` → `html_parser` → 共用 `fifo_matcher`／`report_finance`（TRUNC±1）／`detail_projector`。

---

## 1. 結論摘要

| ID | 現象 | 根因／位置 | 判定 |
|---|---|---|---|
| HIST-01 | 舊 DRAFT（2026-11-20）已配對收入合計較正確值高估 **22,995** | 與玉山 BUG-01 相同：部分配對賣出把整筆 `gross` 拆到已配對片段 | **歷史已確認 Bug**（現況已修復；見新 UAT） |
| — | 現行 master／新 UAT 部分配對收入 | `report_finance.split_sell_gross_with_residual`＋TRUNC | **正常**（四筆部分配對 delta＝0） |
| — | 原始 vs 正規化 65 筆欄位 | `html_parser`＋`statement_html_v1` | **正常**（65/65 全欄一致） |
| — | FIFO 股數／費用一次／A～W／守恆 | 共用投影層 | **正常** |
| BROKER-01 | 24 筆 `INSUFFICIENT_PRIOR_BUYS` | 檔內缺期初庫存；`opening_lots=0`；未配未來買進 | **正常券商／資料缺口**（非漏讀） |
| BROKER-02 | 全檔 `interest=0`；`qty×price` 與 `gross` 全相等 | 群益結算欄位本體 | **正常券商結算差異／特徵** |
| SUSPECT-01 | 舊 DRAFT 無部分配對 W 備註（0 列）；新 UAT 有 4 列 | 舊輸出產於修復前 | **疑似僅歷史輸出落差**（現況已符合 AUD-05） |

**現行程式（`27b411d`）在群益路徑上：未發現需再開修的已確認財務 Bug。**  
玉山已合併之部分配對價金拆分、利息公式、TRUNC±1、未配對守恆欄，對群益同樣生效。

---

## 2. 九項檢查結果

### 2.1 原始交易 vs 正規化

| 項目 | 預期 | 實際 | 結果 |
|---|---|---|---|
| 資料列 | 65 筆交易＋2 總合不入庫 | 來源 67 列；匯入 `trade_count=65`、`excluded_count=2` | OK |
| 買賣 | 買 22／賣 43 | DB `BUY=22`／`SELL=43`；皆 `CASH` | OK |
| 欄位 | 代號／日／價／量／價金／費／稅／息／淨收付 | 以 `.stockCode` 解析後 **65/65** 與 DB 全欄一致 | OK |
| 淨收付守恆 | 買：`net=-(gross+commission)`；賣：`net=gross-commission-tax-interest` | 買 22/22、賣 43/43 | OK |

總合列：`總合(臺幣)` 股數 6,592、金額 1,294,539；`總合(人民幣)` 0——未入庫。

### 2.2 FIFO 買賣股數及成本

| 項目 | 實際 |
|---|---|
| allocations | 30 |
| 每筆來源股數守恆（已配＋未配／未售） | **0** 筆違規 |
| 配套明細列語意 | `MATCHED=30`、`UNSOLD_BUY=8`、`UNMATCHED_SELL=24` |
| 成本合計（新 DRAFT） | 454,049（與舊 DRAFT 成本合計相同） |

### 2.3 部分配對是否高估收入／成本

四筆部分配對賣出（新 UAT）：

| sell 前綴 | 代號 | 日期 | 原始股數 | 已配 | 未配 | 原始價金 | 正確已配價金 | 殘量價金 | 新 DRAFT 收入 | 預期收入 | 高估 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `222a0678` | 3260 | 2026-03-18 | 30 | 20 | 10 | 14325 | 9550 | 4775 | 9495 | 9495（9550−13−42−0） | **0** |
| `8240e855` | 3596 | 2025-11-18 | 65 | 15 | 50 | 11635 | 2685 | 8950 | 2640 | 2640（2685−11−34−0） | **0** |
| `cc101717` | 3596 | 2026-03-24 | 70 | 40 | 30 | 12705 | 7260 | 5445 | 7210 | 7210（7260−12−38−0） | **0** |
| `dd4deb7f` | 3264 | 2026-01-22 | 50 | 25 | 25 | 7650 | 3825 | 3825 | 3796 | 3796（3825−7−22−0） | **0** |

若仍用修復前「整筆 gross 進已配對」演算法，已配對價金合計會高估 **22,995**（4775+8950+5445+3825）。

舊 vs 新 DRAFT 收入合計：

| | 收入合計 | 成本合計 |
|---|---:|---:|
| 舊 `18-51-21` | **348,750** | 454,049 |
| 新 `12-50-34` | **325,755** | 454,049 |
| 差 | **−22,995** | 0 |

→ **HIST-01**：舊輸出證實歷史 Bug；現行輸出已正確。

### 2.4 股數 × 單價整數截斷

DB 65 筆：`TRUNC(qty×unit_price) − gross_amount` **全部為 0**。  
守恆表 `D_difference` 全 0；`out_of_tolerance` 無；`amount_conservation_issue_count=0`。

本檔**沒有**實際截斷尾差案例，但共用層仍執行 TRUNC 規則（見下節）。

### 2.5 是否沿用玉山 TRUNC＋±1

| 項目 | 結論 |
|---|---|
| 實作 | 共用 `backend/services/report_finance.py`：`trunc_toward_zero`、`AMOUNT_TOLERANCE=1`、超限 `AMOUNT_CONSERVATION_OUT_OF_TOLERANCE` |
| 群益本檔 | 無需觸發 ±1 補差；亦無超限列 |
| 是否另寫群益專用規則 | **不需要**；沿用已驗證共用規則即可 |

### 2.6 買／賣手續費、交易稅、利息歸屬

| 檢查 | 結果 |
|---|---|
| 一賣多片段：賣費／稅只落一次 | 5 組多片段賣出皆 `fee_nz=1`、`tax_nz=1`，合計＝來源 |
| 一買多片段：買費只落一次 | 8 組多片段買進皆 `fee_nz=1`，合計＝來源 |
| 利息 | 65 筆皆明確 `0`；收入公式含 −interest（金額影響 0） |
| 部分配對費用 | 落在已配對第一片段；`UNMATCHED_SELL` 殘量列費／稅為 0（費用不重複） |

### 2.7 每筆原始交易股數／價金／費用／淨收入守恆

| 層級 | 結果 |
|---|---|
| 來源淨收付 vs 元件 | 買／賣全數成立（見 2.1） |
| 價金費用守恆 CSV | **65/65** `F_conservation_ok=true` |
| audit | `conservation_ok=true` |
| 部分配對 | `matched_gross + unmatched_gross = source_gross`（四筆皆成立） |

### 2.8 A～W 23 欄契約

| 項目 | 結果 |
|---|---|
| 欄數／欄名 | 23；與 `field_schema.DETAIL_FIELDS` 一致 |
| 合計列 | 0 |
| 明細列 | 38（與 audit `detail_row_count` 一致） |
| 部分配對 W 備註 | 4 列含「費用全額落點；尚有未配對殘量；本列損益非完整原始交易損益」 |

### 2.9 未配對與期初庫存不足

| 項目 | 結果 |
|---|---|
| blocking | 24 筆，皆 `INSUFFICIENT_PRIOR_BUYS` |
| `ORDER_AMBIGUITY` | 0 |
| `opening_lots` | 0 |
| 漏讀證據 | 無（來源 65＝DB 65；未配未來買進） |
| exceptions 守恆欄 | `matched_quantity`／`matched_gross`／`unmatched_gross`／`amount_conservation_ok` 皆有（在 `detail_json`） |

---

## 3. 分級問題清單

### 3.1 已確認 Bug

| ID | 狀態 | 證據 | 預期 | 實際（當下） |
|---|---|---|---|---|
| HIST-01 | **歷史**（已由玉山財務修復消除） | 舊 DRAFT 收入 348,750 vs 新 325,755；四筆部分配對若吃全額則已配價金多計 22,995 | 已配對收入僅片段價金−費稅息 | 舊輸出高估 22,995；**新 UAT＝預期** |

**現行 master 無新增「確認 Bug」列。**

### 3.2 疑似問題

| ID | 說明 | 證據 | 建議 |
|---|---|---|---|
| SUSPECT-01 | 舊群益 DRAFT 無 W 部分配對註記 | 舊 `rows_with_note=0`；新＝4 | 視為歷史輸出；無需修碼。若需留痕可於人工 UAT 註明勿用舊 DRAFT 驗 AUD-05 |

未將「exceptions.csv 頂層無獨立 `matched_gross` 欄（僅在 `detail_json`）」列為疑似缺陷：內容已滿足 AUD-04，與玉山修復後行為一致。

### 3.3 正常券商結算／資料差異

| ID | 說明 | 證據 |
|---|---|---|
| BROKER-01 | 缺期初導致 24 筆 blocking；正式報表應擋、DRAFT+`--allow-partial` 正確 | 見 §4；檔內多檔淨部位為負且存在更晚 BUY 未被誤配 |
| BROKER-02 | 利息全為明確 `0` | DB／來源 65 筆 |
| BROKER-03 | 本檔無 `qty×price` 與 `gross` 尾差 | 65 筆 diff＝0；非缺 TRUNC，而是結算已對齊 |
| BROKER-04 | 僅現股 CASH，無 DAY_TRADE | `trade_types=['CASH']` |

---

## 4. 二十四筆 `INSUFFICIENT_PRIOR_BUYS` 複核

帳戶單一；皆 CASH 池；**不造假買進**。池淨部位以「該賣出之前同代號買賣」估算；結論均為**缺期初**（或前期賣出已耗盡檔內買進），**非漏讀**。

### 4.1 3260（13）

| sell 前綴 | 賣出日 | 賣量 | 已配 | 未配 | unmatched_gross | 結論 |
|---|---|---:|---:|---:|---:|---|
| `1ca1f2af` | 2025-10-03 | 250 | 0 | 250 | 43000 | 檔內此前無 BUY；**缺期初** |
| `c4a77124` | 2025-10-20 | 200 | 0 | 200 | 37500 | 同上延續負部位 |
| `ef9b1fb3` | 2025-10-30 | 50 | 0 | 50 | 9825 | 同上 |
| `6fa27272` | 2025-11-12 | 150 | 0 | 150 | 32400 | 同上 |
| `647311ed` | 2025-12-24 | 150 | 0 | 150 | 33525 | 同上 |
| `9073a9fa` | 2025-12-30 | 100 | 0 | 100 | 25550 | 同上 |
| `ebdcf278` | 2026-01-02 | 100 | 0 | 100 | 27900 | 同上 |
| `20839fcd` | 2026-01-14 | 100 | 0 | 100 | 27300 | 同上 |
| `359b52c8` | 2026-01-19 | 100 | 0 | 100 | 31850 | 同上 |
| `c31f09f9` | 2026-01-20 | 50 | 0 | 50 | 15250 | 同上 |
| `98e09d5a` | 2026-01-22 | 50 | 0 | 50 | 14900 | 同上 |
| `aaa52839` | 2026-02-04 | 100 | 0 | 100 | 33450 | 同上 |
| `222a0678` | 2026-03-18 | 30 | 20 | 10 | 4775 | 僅耗用後期買進殘量 20；餘 10 **缺期初**；不得再配 |

### 4.2 3264（6）

| sell 前綴 | 賣出日 | 賣量 | 已配 | 未配 | unmatched_gross | 結論 |
|---|---|---:|---:|---:|---:|---|
| `15b8494c` | 2025-10-15 | 125 | 0 | 125 | 10037 | 此前無 BUY；**缺期初** |
| `dd4deb7f` | 2026-01-22 | 50 | 25 | 25 | 3825 | 部分配對；殘量缺期初 |
| `cc6374b9` | 2026-02-06 | 150 | 0 | 150 | 21600 | 池已負；不配未來 BUY |
| `cfabc5b3` | 2026-02-10 | 150 | 0 | 150 | 23700 | 同上 |
| `233bf9a1` | 2026-02-26 | 100 | 0 | 100 | 15500 | 同上 |
| `dfa08be3` | 2026-03-02 | 200 | 0 | 200 | 30200 | 同上 |

### 4.3 3596（5）

| sell 前綴 | 賣出日 | 賣量 | 已配 | 未配 | unmatched_gross | 結論 |
|---|---|---:|---:|---:|---:|---|
| `071e3bc5` | 2025-10-14 | 130 | 0 | 130 | 26455 | 此前無 BUY；**缺期初** |
| `8240e855` | 2025-11-18 | 65 | 15 | 50 | 8950 | 部分配對；殘量缺期初 |
| `3a7c8944` | 2025-11-19 | 60 | 0 | 60 | 10890 | 池負；不配未來 |
| `cc101717` | 2026-03-24 | 70 | 40 | 30 | 5445 | 部分配對；殘量缺期初 |
| `c31f5881` | 2026-03-24 | 110 | 0 | 110 | 19965 | 同日另一賣；無剩餘 lot |

代號檔內買賣淨額（買−賣）：3260 **−1380**、3264 **−140**、3596 **−200**（另有已完整配對之 2404／3680／4770 等）。與大量 blocking 一致。

---

## 5. 舊／新 UAT 高階對照

| 指標 | 舊 `18-51-21` | 新 `12-50-34` |
|---|---:|---:|
| trade / buy / sell | 65 / 22 / 43 | 65 / 22 / 43 |
| allocations / issues | 30 / 24 | 30 / 24 |
| conservation_ok | true | true |
| commission_total / tax_total | 1195 / 2501 | 1195 / 2501 |
| detail_row_count | 38 | 38 |
| 收入合計 | 348750 | 325755 |
| 成本合計 | 454049 | 454049 |
| 部分配對 W 註記列數 | 0 | 4 |
| 配套 FIFO／守恆 CSV | （舊流程可能未齊） | 已產出 |

正式 `data/trading.db`、`input/群益.xls`、兩份舊 DRAFT、玉山 `output/uat_esun*` **均未改動**。

---

## 6. 建議 TDD 修正範圍（僅建議，本階段不實作）

現行群益路徑**無必須 GREEN 的生產 Bug**。建議待你確認後，Phase 2 可選：

1. **回歸強化（建議優先，非修 Bug）**  
   - 以**合成** `statement_html_v1` HTML 覆蓋：部分配對四態（全配／部分／全未配）、費用一次、A～W 註記、exceptions `detail_json` 守恆欄。  
   - 斷言收入不得等於「整筆 gross−費稅」（防 HIST-01 回歸）。  
   - **不得**把真實 `群益.xls` 進 fixtures。

2. **不建議再開的修碼**  
   - 群益專用 TRUNC 規則（共用已足夠；本檔甚至無尾差）。  
   - 為消除 24 筆 blocking 而虛構 `opening_lots`／改 FIFO 配未來買進。

3. **產品／資料後續（非財務 Bug）**  
   - 若要出正式（非 DRAFT）群益報表：需**核准**匯入期初 `opening_lots` 後再跑 FIFO。  
   - 可另開需求：期初匯入 CLI／審核流程（屬新功能 TDD，非本 RCA 必修）。

4. **文件**  
   - Phase 2 若做回歸測試，再更新 `TDD_STATUS.md`；本 Phase 1 **不**改 STATUS／SPEC／PRD（無新契約缺口）。

---

## 7. 重現指令（隔離，不動正式 DB）

```powershell
cd C:\Users\billh\python_test\trading_report
uv run pytest -q
uv run python -m backend.cli db init --db data/uat_capital.db
uv run python -m backend.cli import apply --file "input/群益.xls" --broker "群益" --account "main" --profile statement_html_v1 --db data/uat_capital.db
uv run python -m backend.cli match fifo --account "main" --db data/uat_capital.db
uv run python -m backend.cli report detail --account "main" --allow-partial --output-dir output/uat_capital --db data/uat_capital.db
```

本機分析腳本（非正式產品）：`scripts/_capital_rca_audit.py`、`scripts/_capital_rca_audit2.py`。

---

## 8. Phase 1 停止點（已完成）

- RCA 與問題分級已完成；已確認採 **合成回歸**（非期初庫存功能）。

## 9. Phase 2 合成回歸（已執行）

| 項目 | 內容 |
|---|---|
| 測試 | `tests/test_capital_html_finance_regression.py`（4 案） |
| 覆蓋 | HIST-01 防回歸、費用一次、非零利息扣減、早賣 DRAFT／exceptions 守恆、A～W |
| 判定 | **特徵化／回歸**（現況已正確；非虛構 RED；無新業務碼） |
| 全量 | `uv run pytest -q` → **94 passed**（2026-11-21） |
| 狀態 | 見 `docs/test/TDD_STATUS.md` §1.9／§6.2 `capital_html_finance_regression_v1` |
