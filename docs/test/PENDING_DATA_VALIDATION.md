# 待資料驗證登記（PENDING_DATA）

> 狀態語意：`PENDING_DATA` ≠ `PASS`。資料齊全後依本檔重啟驗證邏輯；**不得**為滿足 CR 而偽造交易。

## GOLD-CR-02：原始資料獨立 Reviewer 驗證

| 欄位 | 內容 |
|---|---|
| CR ID | GOLD-CR-02 |
| 問題名稱 | 原始黃金來源須由獨立 Reviewer 在本機驗證指紋／計數／交叉摘要 |
| 程式位置 | `scripts/_golden_phase01_inventory.py`；本機 `data/golden/evidence/`（gitignored） |
| 目前行為 | 盤點腳本可產出 evidence；公開 Git 僅有非敏感規範／模板 |
| 已驗證範圍 | 開發端本機盤點前／後指紋一致；公開摘要已推送 |
| 未驗證範圍 | 獨立 Reviewer 對 ZIP／本機 evidence 的逐項覆核簽核 |
| 缺少資料 | Reviewer 可存取之本機 ZIP 或同等唯讀環境 |
| 資料齊全後 | Reviewer 簽核紀錄寫入本檔或 PR；不符則 FAIL |
| 未來驗收條件 | 獨立覆核 PASS 且與 `phase01_summary` 公開欄位一致 |
| 重新啟動條件 | Reviewer 取得 ZIP／本機 golden 並完成覆核 |
| 目前狀態 | PENDING_DATA |

## GOLD-CR-10：HTML-xls／玉山路徑列級非法分計（擴充範圍）

| 欄位 | 內容 |
|---|---|
| CR ID | GOLD-CR-10（擴充） |
| 問題名稱 | capital CSV 已 invalid／excluded 分計並阻擋 PASS；HTML-xls／玉山尚未同等分類 |
| 程式位置 | `classify_capital_csv_row`／`build_capital_csv_analysis_from_rows`／`csv_acceptance_gate`；`analyze_html_xls`／`analyze_esun_xlsx`／`unresolved_invalid_row_count` |
| 目前行為 | CSV 路徑：非法列分開統計並可阻擋 PASS；HTML／玉山 **`invalid_row_count=UNKNOWN`**（不得預設 0） |
| 已驗證範圍 | 純函式＋合成列／合成 SQLite（CSV 非法列阻擋）；UNKNOWN 語意單元測 |
| 未驗證範圍 | HTML-xls／玉山真實來源之同等 invalid 分計與阻擋 |
| 缺少資料 | 無需新交易測資；待對齊既有 parser 排除語意後擴充 |
| 資料齊全後 | 三來源統一 invalid≠excluded；有非法列不得 PASS；Manifest 改回整數計數 |
| 未來驗收條件 | 任一來源 invalid_row_count>0 → 盤點／交叉非完整成功 |
| 重新啟動條件 | Owner 授權擴充非 CSV 路徑分類（不重開 Phase 0／1 基礎建設） |
| 目前狀態 | PENDING_DATA（CSV 核心已結；其他格式擴充待辦；已標 UNKNOWN） |

## GOLD-CR-05：尚缺來源欄位的完整性驗證

| 欄位 | 內容 |
|---|---|
| CR ID | GOLD-CR-05 |
| 問題名稱 | CSV 無 `raw_row_id`／`trade_id`／batch 等欄；完整性僅能部分交叉 |
| 程式位置 | `scripts/_golden_phase01_inventory.py`::`cross_check_csv_to_db`／`classify_capital_csv_row` |
| 目前行為 | 缺欄標 `NOT_IN_SOURCE`；不以 DB 列取代 A；**已可核對** trade_type／currency（來源有幣別時）／account↔batch／parse_status／來源列相對序 |
| 已驗證範圍 | 代號／買賣／日期／價量／費稅息／淨收付；以及上列可立即核對欄（純函式＋合成 SQLite） |
| 未驗證範圍 | 來源端原生 id 對帳；列序與 raw_row 一對一契約之獨立真實憑證 |
| 缺少資料 | 券商匯出若未來提供穩定外部 trade id／列指紋欄 |
| 資料齊全後 | 擴充交叉鍵納入外部 id；缺則維持 NOT_IN_SOURCE 且不得補造 |
| 未來驗收條件 | 外部 id 存在時 100% 對上；不存在時明確 NOT_IN_SOURCE |
| 重新啟動條件 | 新來源格式含可追溯外部鍵 |
| 目前狀態 | PENDING_DATA（外部鍵仍缺；可立即核對欄已補強） |

## GOLD-CR-11：多帳戶／多批次真實情境

| 欄位 | 內容 |
|---|---|
| CR ID | GOLD-CR-11 |
| 問題名稱 | 多帳戶、多 broker、批次歧義下的來源鎖定與禁止混配 |
| 程式位置 | `scripts/_golden_phase01_inventory.py`::`resolve_batches_by_sha256`／`cross_check_csv_to_db` |
| 目前行為 | 同 `file_sha256` 多批次 → `AMBIGUOUS`／FAIL，**不得** `fetchone` 任意選第一筆 |
| 已驗證範圍 | 純函式／合成 SQLite：0 筆 NONE、1 筆 OK、多筆 AMBIGUOUS |
| 未驗證範圍 | 真實多帳戶同代號、同檔重匯端到端驗收 |
| 缺少資料 | 真實多帳戶／重匯批次樣本（不得自造） |
| 資料齊全後 | 以真實歧義樣本重跑盤點；確認零混配 |
| 未來驗收條件 | 多帳戶案例下零混配；歧義必失敗 |
| 重新啟動條件 | Owner 提供可重用之多帳戶真實封存 |
| 目前狀態 | PENDING_DATA（歧義偵測已實作；完整多帳戶仍待資料） |

## 玉山歷史交易缺少期初買進資料

| 欄位 | 內容 |
|---|---|
| CR ID | GOLD-ESUN-OPENING |
| 問題名稱 | 玉山 2236（及其他）缺買進來源時不得混配群益或自造期初 |
| 程式位置 | GOLD-003 Manifest `known_limitations`；FIFO／opening 相關服務（未在本輪改） |
| 目前行為 | Manifest 註記 SELL-only；禁止混配／自造期初 |
| 已驗證範圍 | 盤點確認缺買進事實 |
| 未驗證範圍 | 取得真實期初後的 FIFO／損益端到端 |
| 缺少資料 | 玉山期初庫存核准來源或更早買進對帳單 |
| 資料齊全後 | 經核准 opening_lots 或補匯後重跑真實驗收 |
| 未來驗收條件 | 有期初憑證才允許該代號完整財務 PASS |
| 重新啟動條件 | Owner 核准期初或提供更早來源 |
| 目前狀態 | PENDING_DATA |

## 特殊商品及特殊交易類型

| 欄位 | 內容 |
|---|---|
| CR ID | GOLD-SPECIAL-INSTRUMENT |
| 問題名稱 | ETF／特殊證券／非台股／未支援交易類型之真實驗收 |
| 程式位置 | `backend/services/day_trade_annotation.py`（稅／商品分類）；ingest unsupported 路徑 |
| 目前行為 | 啟發式／INSUFFICIENT；未當作已確認商品主檔 |
| 已驗證範圍 | 合成／契約測（非真實帳戶黃金） |
| 未驗證範圍 | 真實特殊商品完整稅與 FIFO 邊界 |
| 缺少資料 | 足夠真實特殊商品成交樣本 |
| 資料齊全後 | 依商品／稅規則版本擴充證據；不足仍 INSUFFICIENT |
| 未來驗收條件 | 特殊商品不得被誤標已確認適用 |
| 重新啟動條件 | 真實樣本入 archive 並完成 Manifest |
| 目前狀態 | PENDING_DATA |

## 尚無足夠真實資料的逐筆財務邊界情境

| 欄位 | 內容 |
|---|---|
| CR ID | GOLD-FIN-EDGE |
| 問題名稱 | 零股、尾差、部分配對、跨年等真實逐筆財務邊界 |
| 程式位置 | `scripts/uat_fifo_same_day_2236.py`::`verify_detail_xlsx_finance`；`backend/golden/compare_c_d.py` |
| 目前行為 | GOLD-001-2236 已完成本機 C↔D 聚合／指紋／故障注入；其他邊界樣本仍缺 |
| 已驗證範圍 | GOLD-001-2236 隔離 UAT；合成 C↔D；RED-07 逐筆互抵；INV-05 同向偏移 |
| 未驗證範圍 | 零股／跨年／特殊尾差等其他真實片段全覆蓋；GOLD-004 全年 D 端到端 |
| 缺少資料 | 對應邊界之真實對帳單片段（不得為滿足 CR 而自造） |
| 資料齊全後 | 擴充本機 C↔D 案例；缺資料不預設 PASS |
| 未來驗收條件 | 各邊界獨立 C 與正式管線一致 |
| 重新啟動條件 | Owner 提供可重用邊界封存 |
| 目前狀態 | PENDING_DATA（001-2236 已驗；其餘邊界仍待） |

## 受測 report_finance 負數 TRUNC 語意（與 C 層分離）

| 欄位 | 內容 |
|---|---|
| CR ID | GOLD-TRUNC-NEG |
| 問題名稱 | 受測 `backend.services.report_finance.trunc_toward_zero` 對負數使用 `ROUND_UP`（離零），與 Decimal「朝零＝ROUND_DOWN」不符 |
| 程式位置 | `backend/services/report_finance.py`::`trunc_toward_zero` |
| 目前行為 | **已修正**：正負數一律 `ROUND_DOWN`（朝零） |
| 已驗證範圍 | 合成負數契約測＋既有正數 `test_fragment_gross_trunc` 回歸 |
| 未驗證範圍 | （無；本項結案） |
| 缺少資料 | 無 |
| 資料齊全後 | — |
| 未來驗收條件 | 正負數皆朝零；與獨立 C 一致 |
| 重新啟動條件 | — |
| 目前狀態 | **CLOSED**（Phase 3／CR-10A 接回已修） |

## GOLD-002／003／004 適用範圍（Phase 3）

| case | 驗收 | 待資料／限制 |
|---|---|---|
| GOLD-002 | PARTIAL：來源 PARTIAL、可算 FIFO／aggregates；不得完整成功 | HTML `invalid_row_count=UNKNOWN`；realized 因未配賣出不完全 |
| GOLD-003 | PARTIAL：已確認缺買進／未知幣別／非 CASH 類型欄 | 期初、DAY_TRADE pool、幣別；**不得補造期初／預設 0** |
| GOLD-004 | C 層 `INDEPENDENTLY_COMPUTED`＋來源 PASS（本機） | 全年 D 端到端 UAT 尚未跑（504 筆）；非阻擋 CR-10A 2236 |

本機摘要：`data/golden/evidence/phase03_partial_cases_summary.json`（gitignored）。

## 延期（DEFERRED；本輪非阻擋）

| ID | 說明 | 狀態 |
|---|---|---|
| CR-10A GOLD-001-2236 | 本機隔離 UAT C↔D **PASS**；證據本機 `runs_d` | **本輪已驗**（真實數字不入 Git） |
| CR-10B／10C | 合成檔案層故障注入＋`uat_exit_code`；真實報表反向見 2236 UAT | 部分完成；擴充案例非阻擋 |
| CR-06B／06C | 既有合成九筆 E2E 維持 | 既有通過 |
| GOLD-004 全年 D UAT | C 已就緒；正式管線全年比對 | DEFERRED（資料量大；非 2236 阻擋） |
| Manifest Pydantic／mypy／Hypothesis／Mutation／完整稅務引擎 | 獨立評估 | DEFERRED |
