# PR #12 — 原始 CR-01～13 最終銷帳表

> **文件性質**：原始 Code Review 銷帳（Class C）。**不得**將 GOLD-CR／GOLDEN Phase 0～5 結案直接等同本表原始 CR 結案。  
> **基準**：PR #12 歷次 Reviewer 留言、SPEC、`TDD_STATUS.md`、本機測試／UAT；Commit tip 見推送後 SHA。  
> **Merge Readiness**：**暫停 Merge**（Owner：須完成測試資料來源／誠信稽核）；見 `PR12_TEST_DATA_SOURCE_AUDIT.md`。  
> **禁止**：Merge、正式 Migration、寫入正式 DB、偽造交易／期初／假報表。

## 0. 狀態語意

| 狀態 | 意義 |
|---|---|
| `RESOLVED` | 原始要求已有對應修正＋可重跑驗收證據；無阻擋 Merge 的已知缺口 |
| `PASS_WITH_NOTES` | 核心要求已驗；殘餘限制／文件注意事項，**非**以測試數量冒充結案 |
| `PARTIAL` | 原始要求僅部分覆蓋 |
| `PENDING_DATA` | 缺真實資料／外部環境；不得 PASS |
| `NOT_VERIFIED` | 尚無足夠獨立驗收證據 |
| `DEFERRED` | 明確延期，非本 PR 阻擋 |
| `OPEN` | 仍開著、需再修 |
| `BLOCKER` | 確認阻擋 Merge |

---

## 1. 總覽（原始 CR；含子項）

| CR ID | 最新狀態 | 阻擋 Merge？ |
|---|---|---|
| CR-01 | RESOLVED | 否 |
| CR-02（含 02A／02B／02C） | PASS_WITH_NOTES | 否（啟發式≠主檔；非完整稅務引擎） |
| CR-03 | RESOLVED | 否 |
| CR-04 | RESOLVED | 否 |
| CR-05 | PASS_WITH_NOTES | 否（lossy downgrade／正式回滾靠備份） |
| CR-06（母項） | PASS_WITH_NOTES | 否（見 06A～C；真實帳戶副本 UAT 未重跑） |
| CR-06A | RESOLVED | 否 |
| CR-06B | PASS_WITH_NOTES | 否（Excel 聚合已驗；逐筆成本／收入主要經 Trace↔C／CR-10A） |
| CR-06C | PASS_WITH_NOTES | 否（第一片段 sequence 對位已驗；非零利息真實樣本 PENDING_DATA） |
| CR-07 | RESOLVED | 否 |
| CR-08 | RESOLVED | 否 |
| CR-09 | RESOLVED | 否 |
| CR-10（母項） | PASS_WITH_NOTES | 否（見 10A～C） |
| CR-10A | PASS_WITH_NOTES | 否（Excel 未宣稱全面逐欄；見未驗證範圍） |
| CR-10B | RESOLVED | 否 |
| CR-10C | RESOLVED | 否 |
| CR-11 | PASS_WITH_NOTES | 否（指紋限無並發寫入前提） |
| CR-12 | RESOLVED | 否 |
| CR-13 | PASS_WITH_NOTES | 否（Ruff D 未全面強制） |

**本表無 `BLOCKER`／`OPEN` 原始 CR。** 殘餘為 NOTES／PENDING_DATA（見 §3、§4）。

---

## 2. 逐項銷帳

### CR-01 — 疑似當沖支持股數高估

| 欄位 | 內容 |
|---|---|
| 原始要求 | `suspected_support_qty = min(buy_qty, half_rate_sell_qty)`，不得整組賣出股數 |
| 對應修正 | `backend/services/day_trade_annotation.py` |
| 實際驗收 | `tests/test_day_trade_annotation.py`；2236 E2E／original import `suspected==1000`；Reviewer Round-2+ **RESOLVED** |
| 最新狀態 | **RESOLVED** |
| 剩餘問題 | 無 |
| 阻擋 Merge | 否 |

### CR-02 — 交易稅適用範圍（含 02A／02B／02C）

| 欄位 | 內容 |
|---|---|
| 原始要求 | 固定 0.003／0.0015 須綁商品／幣別／類型／日期；不足 → `INSUFFICIENT_EVIDENCE`；不得強制推論 |
| 對應修正 | `day_trade_annotation.py`（`tw_sec_tax_v3`）；SPEC AUD-DT-01 |
| 子項 | **02A** 一般稅 vs 減半稅期間分開；核實期限≠法令日落。**02B** audit 記錄 rounding／tolerance／source_verified。**02C** 衝突 → `MIXED_INSTRUMENT_EVIDENCE`，不得 `sells[0]` |
| 實際驗收 | `test_cr02_*`／`test_cr02c_mixed_*`；與 SPEC：`TWD`＋`CASH`＋`gross>0`＋`INFERRED_TW_COMMON_STOCK`；半稅 ≥2017-04-28；核實至 2026-12-31 |
| 最新狀態 | **PASS_WITH_NOTES** |
| 剩餘問題 | 四碼啟發式 ≠ 商品主檔；非完整稅務引擎；特殊商品真實樣本見 GOLD-SPECIAL-INSTRUMENT（PENDING_DATA，分列） |
| 阻擋 Merge | 否 |

### CR-03 — 稅額容差重疊

| 欄位 | 內容 |
|---|---|
| 原始要求 | 雙容差 → `AMBIGUOUS_TAX_EVIDENCE`；明確 Decimal rounding |
| 對應修正 | `day_trade_annotation.py`（`ROUND_HALF_UP`；AMBIGUOUS 優先於 HALF_RATE） |
| 實際驗收 | `test_cr03_*`；Reviewer 自 Round-2 **RESOLVED** |
| 最新狀態 | **RESOLVED** |
| 剩餘問題 | 無（取整依據文件併 CR-02B） |
| 阻擋 Merge | 否 |

### CR-04 — Annotation 例外隔離

| 欄位 | 內容 |
|---|---|
| 原始要求 | 全包 try／except；失敗不中斷報表；`ANNOTATION_FAILED`／FAILED |
| 對應修正 | `report_service` annotation prep／分析／serialization 隔離；OFF 跳過 prep |
| 實際驗收 | `test_annotation_report_noninterfere`（prep fault／OFF）；Round-2+ **RESOLVED** |
| 最新狀態 | **RESOLVED** |
| 剩餘問題 | 無 |
| 阻擋 Merge | 否 |

### CR-05 — Migration 歷史配對分類

| 欄位 | 內容 |
|---|---|
| 原始要求 | 可靠 backfill；upgrade／downgrade／FK／row／財務完整性；勿將 DAY_TRADE 誤標 STANDARD |
| 對應修正 | Alembic `b2c3d4e5f6a7`；UAT `migration_probe` |
| 實際驗收 | `test_match_type_migration_*`；opening lot／財務欄／FK／integrity；lossy downgrade 文件化 |
| 最新狀態 | **PASS_WITH_NOTES** |
| 剩餘問題 | v3 `SAME_DAY_RECONCILED` downgrade 不可還原；正式回滾靠備份；**未**對正式 DB 執行 migrate |
| 阻擋 Merge | 否 |

### CR-06 — 2236 原始案例（母項）

| 欄位 | 內容 |
|---|---|
| 原始要求 | 原始九筆 Parser→Import→FIFO→Report；Pass1=3600／Pass2=400／suspected=1000；Decimal golden |
| 對應修正 | `tests/test_fifo_same_day_2236_original_import_e2e.py`；合成 E2E 另檔 |
| 最新狀態 | **PASS_WITH_NOTES**（細節見 06A～C） |
| 剩餘問題 | 完整真實帳戶一致性副本隔離 UAT **未**重跑（PENDING_DATA／環境，非本表 BLOCKER） |
| 阻擋 Merge | 否 |

### CR-06A — Owner canonical 列序

| 欄位 | 內容 |
|---|---|
| 原始要求 | 0828：SELL145→SELL290→BUY；0902：579→21；不得宣稱合成序為 Owner 序 |
| 對應修正 | `ORIGINAL_ROWS`；`test_cr06_canonical_owner_row_order` |
| 實際驗收 | 上列斷言＋canonical pipeline |
| 最新狀態 | **RESOLVED** |
| 剩餘問題 | 真實對帳單檔案層 UAT 未重跑（與母項同） |
| 阻擋 Merge | 否 |

### CR-06B — Excel 財務（canonical＋permutation）

| 欄位 | 內容 |
|---|---|
| 原始要求 | permutation 須跑與 canonical 相同 Excel 財務驗收（股數／費稅／成本／收入／損益／淨收付／守恆等） |
| 對應修正 | `_assert_excel_finance`；`test_cr06_*` |
| 實際驗收 | canonical＋全部 permutation 呼叫 `_assert_excel_finance`；本機優先套件 **通過** |
| 與獨立 C／Trace | GOLD-001-2236 Phase 3：聚合 Excel↔C＋Trace↔C 逐筆成本／收入（**加強證據，非以 GOLD 取代本 CR**） |
| 最新狀態 | **PASS_WITH_NOTES** |
| 剩餘問題 | 原始 CR-06B 驗收器 golden 來自列 fixture（非獨立 C）；逐筆成本／收入以 Trace／CR-10A 為主；Excel 逐欄未全面宣稱 |
| 阻擋 Merge | 否 |

### CR-06C — 逐筆費用／價金落點

| 欄位 | 內容 |
|---|---|
| 原始要求 | 以實際 Trace／輸出證明：買賣手續費、交易稅、適用利息、片段價金、費用第一片段落點；後續片段不重複 |
| 對應修正 | `_assert_per_trade_fees_from_trace`＋`_assert_independent_c_fee_on_first_fragment` |
| 實際驗收範圍 | **(1)** Trace MATCHED 列以 `allocation_id`→`sequence_no` 對位：第一片段手續費／稅／利息＝交易原值；後續片段皆 0。**(2)** 不得僅以非零列數＝1 結案。**(3)** 實際 Excel：買／賣手續費與稅加總＝golden；買方非零列數＝BUY 筆數。**(4)** 獨立 C `allocation_lines`（同源 canonical／permutation fixture，非虛假新資料）：買賣費用只在各 trade 首次出現片段；`gross_conservation_ok`。**(5)** 片段價金重用 `allocate_trade_fragment_amounts`（TRUNC／±1）＋`quantity_conservation`。**(6)** Pass1／Pass2 依第一片段 `match_type` 歸屬加總。**(7)** 579 價金≠單價×股數既有斷言仍保留。 |
| 最新狀態 | **PASS_WITH_NOTES** |
| 剩餘問題 | 本 fixture **已知利息皆 0**（第一片段明確寫 0 已驗）；**非零利息真實樣本**維持 **PENDING_DATA**（不得宣稱為 PASS） |
| 阻擋 Merge | 否 |

### CR-07 — 財務非干涉（Annotation ON／OFF）

| 欄位 | 內容 |
|---|---|
| 原始要求 | ON／OFF 完整比較財務欄／守恆 |
| 對應修正 | `test_annotation_report_noninterfere`；`REQUIRED_AUDIT_KEYS` |
| 實際驗收 | Round-3／4 Reviewer **已解決** |
| 最新狀態 | **RESOLVED** |
| 剩餘問題 | 無 |
| 阻擋 Merge | 否 |

### CR-08 — 實際例外注入

| 欄位 | 內容 |
|---|---|
| 原始要求 | monkeypatch fault → ANNOTATION_FAILED；不得空 warnings 冒充 |
| 對應修正 | report／annotation fault 測試 |
| 實際驗收 | Round-2+ **RESOLVED** |
| 最新狀態 | **RESOLVED** |
| 剩餘問題 | 無 |
| 阻擋 Merge | 否 |

### CR-09 — UAT 無效自我比較

| 欄位 | 內容 |
|---|---|
| 原始要求 | 前後不可變財務快照；非 self-compare |
| 對應修正 | UAT `h_ok` snapshot；report ON／OFF |
| 實際驗收 | Round-1 後修正；Reviewer **RESOLVED** |
| 最新狀態 | **RESOLVED** |
| 剩餘問題 | 無 |
| 阻擋 Merge | 否 |

### CR-10 — UAT 最終判定（母項）

| 欄位 | 內容 |
|---|---|
| 原始要求 | 全部步驟後再算 PASS／FAIL；納入 migration／冪等／產出／守恆／完整性 |
| 對應修正 | `build_uat_checks`；`uat_exit_code` |
| 最新狀態 | **PASS_WITH_NOTES**（見 10A～C） |
| 阻擋 Merge | 否 |

### CR-10A — Excel／財務真實驗證（含 GOLDEN 接回後核對）

| 欄位 | 內容 |
|---|---|
| 原始要求 | 移除 `detail_xlsx_finance_ok=True` 預設；讀 Excel vs 獨立 Decimal golden；缺／空白／損毀／錯值 → FAIL；寫入 summary |
| 對應修正 | `scripts/uat_fifo_same_day_2236.py`::`verify_detail_xlsx_finance`；Phase 3 `compare_c_d`／`phase3_pipeline` |
| 實際驗收 | Round-4 檔案層＋verdict；`cr10a_finance_verify_v1`；GOLD-001-2236 UAT **PASS**（聚合 Excel↔C、Trace 逐筆↔C、重複鍵多重集）；Excel 未驗證範圍已記錄 |
| 最新狀態 | **PASS_WITH_NOTES** |
| 剩餘問題 | Excel **未**宣稱 A–W 全面逐欄；逐筆財務以 Trace↔C 為主；原始 CSV Parser 路徑見 GOLD-CSV-PARSER（分列 PENDING） |
| 阻擋 Merge | 否 |

### CR-10B — 實際檔案故障注入

| 欄位 | 內容 |
|---|---|
| 原始要求 | 篡改實際 Excel／audit／刪除產物 → FAIL、非零 exit、failed_checks、summary；正式 DB 不受影響 |
| 對應修正 | `tests/test_uat_fifo_same_day_file_fault.py`；Phase 3 CR-10A UAT fault summary |
| 實際驗收 | 損益／費／稅／空白／損毀／trace／cons／audit；GOLD-001 fault 僅 `detail_xlsx_finance_ok`；觀測自正常 UAT（非固定 True） |
| 最新狀態 | **RESOLVED** |
| 剩餘問題 | 合成路徑未跑之 migration／冪等／H 明確不列入 claimed 證據 |
| 阻擋 Merge | 否 |

### CR-10C — 稽核檔路徑與內容

| 欄位 | 內容 |
|---|---|
| 原始要求 | 用 report 實際路徑；拒同名目錄；格式／必要欄位／守恆結果／audit 型別 |
| 對應修正 | `resolve_required_outputs`；`verify_audit_artifacts_content` |
| 實際驗收 | fault 刪檔／目錄；Conservation `True`/`False` 實際值；`audit.conservation_ok` 一致；GOLD-001／004 artifacts **ok** |
| 最新狀態 | **RESOLVED** |
| 剩餘問題 | 無阻擋項 |
| 阻擋 Merge | 否 |

### CR-11 — UAT 目錄與正式 DB 保護

| 欄位 | 內容 |
|---|---|
| 原始要求 | 唯一 run 目錄；禁 rmtree；path 驗證；WAL／SHM；fingerprint 優於純 mtime |
| 對應修正 | UAT 腳本；`fingerprint_bundle`／compare |
| 實際驗收 | 文件化限制；本機 UAT 指紋 PASS |
| 最新狀態 | **PASS_WITH_NOTES** |
| 剩餘問題 | 指紋前提＝無並發寫入；不宣稱涵蓋 OS／防毒等 |
| 阻擋 Merge | 否 |

### CR-12 — Annotation 可追溯欄

| 欄位 | 內容 |
|---|---|
| 原始要求 | half_rate／same_day ids、suspected、rule version 等（audit JSON） |
| 對應修正 | `annotation_to_audit_dict` |
| 實際驗收 | E2E／annotation 測；Reviewer **RESOLVED** |
| 最新狀態 | **RESOLVED** |
| 剩餘問題 | 無 |
| 阻擋 Merge | 否 |

### CR-13 — Google Style Docstring

| 欄位 | 內容 |
|---|---|
| 原始要求 | 列出 API 補 Args／Returns／Side Effects 等 |
| 對應修正 | 觸及 API docstring；CODING_STANDARDS |
| 實際驗收 | Reviewer PASS WITH NOTES |
| 最新狀態 | **PASS_WITH_NOTES** |
| 剩餘問題 | Ruff D 系列未全面強制為 CI gate |
| 阻擋 Merge | 否 |

---

## 3. 衍生／強化項（屬原始 CR 延伸，非 GOLD-CR）

| ID | 說明 | 狀態 | 阻擋？ |
|---|---|---|---|
| RED-07 | 逐筆成本／收入互抵仍須 FAIL | RESOLVED（verdict／Phase 3） | 否 |
| GOLD-TRUNC-NEG | 受測 `trunc_toward_zero` 負數朝零 | RESOLVED（CLOSED） | 否 |
| 真實帳戶副本 UAT 重跑 | Round-4 checklist | PENDING_DATA | 否（環境／資料；非程式 OPEN） |
| 全股票新舊財務差異 | Round-4 checklist | DEFERRED／PENDING_DATA | 否 |

---

## 4. GOLD-CR／GOLDEN（分開列管；≠ 原始 CR）

> 詳細見 `docs/test/PENDING_DATA_VALIDATION.md` 與 `TDD_STATUS.md` §1.23～1.30。

| ID | 狀態（摘要） | 備註 |
|---|---|---|
| GOLD-CR-01／03／04／06／07／08／09 | CLOSED（Phase 0／1） | 勿回寫為原始 CR-01… |
| GOLD-CR-02 | PENDING_DATA | 獨立 Reviewer 本機覆核 |
| GOLD-CR-05 | PENDING_DATA（外部鍵） | 可立即核對欄已補強 |
| GOLD-CR-10 | CSV 核心 CLOSED；HTML／玉山擴充 PENDING | `invalid_row_count=UNKNOWN` |
| GOLD-CR-11 | 歧義偵測 CLOSED；多帳戶真實 PENDING | |
| GOLD-001-2236 | 本機 UAT PASS | 服務 CR-10A 接回，**不**自動關閉全部原始 CR |
| GOLD-002／003 | PARTIAL | 資料限制 |
| GOLD-004 | 本機 PASS（HTML bridge） | 原始 CSV Parser → GOLD-CSV-PARSER PENDING |
| GOLD-CSV-PARSER | PENDING_DATA | 不得將 bridge 稱 Parser 完整驗收 |
| Phase 0～5 基礎 | 保留；不重開重做 | Merge Readiness 已實查；**待 Owner 最終授權 Merge** |

---

## 5. 本輪優先核對結論

| 優先項 | 結論 |
|---|---|
| CR-02 | 與 SPEC `tw_sec_tax_v3`／AUD-DT-01 **一致**；NOTES＝啟發式與非完整稅引擎 |
| CR-06B | 原始 Excel 聚合驗收 **已落地**；逐筆成本／收入以 Trace↔獨立 C（GOLD-001）加強 |
| CR-06C | Trace sequence 對位＋Excel＋獨立 C **已證明第一片段落點**；非零利息真實樣本 → PENDING_DATA／NOTES |
| CR-10A／B／C | 對回 Round-4 原始要求＋Phase 3 收尾後：**10B／10C RESOLVED**；**10A PASS_WITH_NOTES** |

不得僅以「299 passed」宣稱原始 CR 全部結案；本表逐項對應要求與證據。

---

## 6. 建議 Reviewer 抽查清單

1. `docs/test/PR12_ORIGINAL_CR_WRITEOFF.md`（本檔）與 PR 歷次判定對照  
2. `test_day_trade_annotation`（CR-02／02C）  
3. `test_fifo_same_day_2236_original_import_e2e`（CR-06A／B／C）  
4. `test_uat_fifo_same_day_file_fault`＋GOLD-001 UAT summary（CR-10B／10C）  
5. GOLD-001／004 本機 summary（證據 gitignored）與正式 DB 指紋  
6. 確認 **無** Merge／正式 migrate／寫正式 DB  

---

## 7. 變更紀錄

| 日期 | 說明 |
|---|---|
| 2026-11-26 | 初版：返回原始 CR 完整銷帳；與 GOLD 分列；優先核對 02／06B／06C／10A–C |
| 2026-11-26 | CR-06C 收尾：第一片段 sequence 對位＋獨立 C／Excel／價金守恆；更新實際驗收範圍；啟動 Merge Readiness 實查 |
