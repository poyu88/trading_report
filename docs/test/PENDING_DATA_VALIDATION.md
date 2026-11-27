# 待驗證登記（PENDING_DATA_VALIDATION）

本檔是 **trading_report** **持久化待驗證事項**的唯一正式登記處（產品沿用擴充）。
工程驗收四態定義見 [`../AGENT_INTEGRITY.md`](../AGENT_INTEGRITY.md)；流程與隔離見 [`../DEVELOPMENT_WORKFLOW.md`](../DEVELOPMENT_WORKFLOW.md)。
制度對齊母版 `VERIFICATION_PENDING` 範式，但**不**另建重複文件。

## 用途與規則

- 缺少驗證規則、預期結果、可信資料、環境或權限時，工程驗收層一律列 **`PENDING`**，並在此登記。
- 規則明確、已執行驗證且取得不符合證據時，必須列 **`FAIL`**（不得以 PENDING 掩蓋）。
- 優先完成已具備驗證條件的工作；**不**因個別 PENDING 停止其他可完成項。
- **禁止**虛構規則、資料、預期結果或 PASS 以清除 PENDING。
- **禁止**改寫歷史 FAIL 或工具原生執行證據；僅追加更新。
- 歷史用語 `PENDING_DATA` **保留**作為 Evidence／史實；工程層對應為 `PENDING`（見 Integrity §2.1）。
- `PENDING_DATA` ≠ `PASS`。資料／環境／授權齊全後依本檔重啟驗證；**不得**為滿足 CR 而偽造交易。

## 工程治理欄位（VP-TR 與新增項建議欄位）

| 欄位 | 說明 |
|---|---|
| ID | 穩定識別（建議 `VP-TR-NNN` 或沿用既有 CR ID） |
| Requirement | 待驗證需求摘要 |
| Acceptance Criteria | 可檢查的通過條件（若尚不明，寫明「待補」並留在 PENDING） |
| Status | 工程四態；列管項預設 `PENDING`（完成後可改 `PASS`／`FAIL`／`N/A`） |
| Reason | 為何尚未完成可信驗證，或 FAIL 依據 |
| Evidence | 現有證據路徑／指令／輸出限度（無則寫 `none`） |
| Next Action | 後續增補、重驗條件、所需授權或環境 |

歷史 `PENDING_DATA` 區塊維持原欄位結構（不強制改寫）；新增工程項優先使用上表。

---

## 工程治理待驗證（VP-TR）— Stage D 登錄；Stage E／F 已執行 Runtime（結案追加）

> Stage D 初登錄時 Runtime 未跑。下表為 **Stage E.6 結案追加**後之現況（保留歷史 FAIL／E.3；不因 Merge 清空其他 PENDING）。
> 母版自身 VP-002-D／VP-003 仍 PENDING，不得冒稱本產品已驗證相關母版能力。
> 私人證據以 Evidence ID 引用（`EV-TR-GOV-E4F-*`）；絕對路徑僅在私人 BACKUP_INDEX。

| ID | Requirement | Acceptance Criteria | Status | Reason | Evidence | Next Action |
|---|---|---|---|---|---|---|
| VP-TR-001 | 獨立驗收環境（依風險選 Clean Clone／Worktree／更高隔離）可用且路徑正確 | Workflow §2.10 檢查表可實跑；正式 DB／正式 output 未被誤用；**不得**在持有正式交易資料的工作目錄執行正式 Regression | **PASS** | Clean Clone 於 Owner Temp Root 專案子目錄完成；HEAD＝Acceptance Commit；clone 無正式 DB／無共用 `.venv` | EV-TR-GOV-E4F-REPORT；Acceptance `4019528a…`；PR [#14](https://github.com/poyu88/trading_report/pull/14) | 維持；後續正式 Regression 仍依 §2.10 選隔離 |
| VP-TR-002 | 測試隔離安全確認 | 日常／公開 CI 僅合成／公開 fixture／tmp；經授權私人驗收符合 Gate／隔離路徑；無未授權正式 DB 讀寫 | **PASS** | **範圍限定**：本輪 CI 等效合成／公開 Regression 之隔離稽核。硬編碼外部路徑未見；預設 DB 為 clone-relative 且不存在；正式庫未授權讀寫內容。**Notes**：勿設 `TRADING_DB_PATH` 哨兵覆寫 Alembic Config（見歷史 FAIL 證據） | EV-TR-GOV-E4F-REPORT；EV-TR-GOV-E4F-SENTINEL-FAIL | Migration 副本驗收須重做環境檢查（含 `TRADING_DB_PATH`／`alembic/env.py` 優先序） |
| VP-TR-003 | Lockfile 一致性驗收 | 於**獨立驗收環境** `uv sync --locked --dev` 成功；與 `uv.lock` 一致；記錄 Command／Exit Code | **PASS** | 隔離環境 Exit **0**；Python 3.11.18；lock 未改；獨立 `.venv` | EV-TR-GOV-E4F-UV | 依賴變更時重驗 |
| VP-TR-004 | Pytest 工具執行與需求驗收（分層；非 Overall） | 見下方「VP-TR-004 證據範圍」；各層獨立記錄；**禁止**以 exit 0／CI 綠燈／測試數量替代需求驗收 | **PENDING**（分層見下） | **A** 本機／PR CI／master CI 工具執行均有 Exit 0 證據（**PASS**）。**B** 已執行案例 299 passed；4 skipped（**非 FAIL**）。**C** 缺私人 fixture 之 REAL_DERIVED／CR-06 需求維持 PENDING。**D** 真實 UAT 未授權。**不得**標本 ID 整體 PASS | 本機 EV-TR-GOV-E4F-PYTEST（299／4）；PR CI [`46042047293`](https://github.com/poyu88/trading_report/actions/runs/46042047293)（299 passed, 4 skipped）；master CI [`46042689924`](https://github.com/poyu88/trading_report/actions/runs/46042689924)（299 passed, 4 skipped）；skip 原因見本機 `-ra`：`PRIVATE_FIXTURE_UNAVAILABLE` | 私人測資 Gate 齊全後重驗 C；另案 UAT 重驗 D |
| VP-TR-005 | Migration 副本驗收 | 於**核准副本／測試庫**完成 Migration；正式 DB 未遭未授權變更 | **PENDING** | 缺 Migration 副本環境與 Owner 升級授權；**另案授權**；本輪**未**執行 migrate | Workflow §2.10；none（runtime migrate） | 取得副本＋另案授權；驗收前檢查 `TRADING_DB_PATH` 與 Alembic URL 優先序；禁止對正式 DB 未授權 migrate |
| VP-TR-006 | 正式資料庫升級授權狀態 | 有書面授權紀錄或明確暫不升級依據 | **PENDING** | 尚未取得正式 DB 升級授權；不得自行升級；mtime 一致 ≠ 內容完整性 | none | Owner 書面授權或決定暫不升級並登記依據 |
| VP-TR-007 | 未採用工具後續評估（Mypy／Coverage／Ruff Format CI／Hooks） | 各工具採納或維持 NOT_ADOPTED 的書面決策；評估中不得標 N/A | **PENDING** | 本輪依授權維持 NOT_ADOPTED；評估未完成 | `STANDARDS_VERSION.md` | 另案評估；完成前維持 PENDING／NOT_ADOPTED |

### VP-TR-004 證據範圍（工具執行 ≠ 需求驗收）

必須**分層**記錄；**不得**新建 Overall PASS 聚合器。

| 層 | 意義 | 可標 PASS 的條件 | 不得推論 |
|---|---|---|---|
| A. 工具執行 | `pytest` 程序有真實執行證據 | 記錄 Command、**Exit Code**、輸出摘要 | 不代表所有案例通過；不代表需求／真實業務驗收 |
| B. 個別測試案例 | 單一 test node 結果 | 該案已執行且符合其斷言／契約 | 不代表同需求之其他案例或真實資料驗收 |
| C. 需求驗收 | 對應 PRD／SPEC／Pending 需求項 | 該需求之必要案例皆已依獨立預期結果驗證且通過 | 不因「pytest 綠燈」自動成立 |
| D. 真實資料業務驗收 | Golden／REAL_DERIVED／人工 UAT 等 | 經授權私人測資或 UAT，且符合 Gate／隔離／獨立預期 | 合成通過 ≠ D 完成 |

強制規則：

1. 證據須含適用之原生結果：**Passed／Failed／Skipped／XFailed／XPassed**（或同等 pytest 摘要）**以及 Exit Code**；對 **Skipped**／**XFailed** 須記錄**可審查的原因**（如 skip mark／訊息／缺私人測資）。
2. Exit Code `0` **不代表**「所有測試案例及需求均已通過」（例如存在 skip／xfail、或未覆蓋之需求）。
3. 因缺少私人測資而 **Skipped**（或同等未執行）的測試 → 其**對應需求驗收**維持 **`PENDING`**（不得標 PASS／N/A）。
4. 已執行且符合明確驗收條件 → 該案例／需求可標 **`PASS`**。
5. 已取得不符合要求的證據 → 標 **`FAIL`**（不得降級為 PENDING）。
6. **禁止**以工具成功、CI 綠燈或測試**數量**替代個別需求驗收。

---

## Stage E Independent CR 歷史結論（保留；不得覆寫）

| 欄位 | 內容 |
|---|---|
| 審查 | Stage E Independent CR（唯讀；對話紀錄） |
| 分支 | `docs/adopt-governance-1.1` @ `0c0a65d2…`（未 Commit WC） |
| 結論 | **FAIL**（Owner 已接受） |
| Findings | TR-CR-01（Pytest 驗收誠信；同源 F-01）、TR-CR-02（私人測資邊界）、TR-CR-03（Merge／Regression 順序）、TR-CR-04（README FIFO 與 SPEC 不一致）、TR-CR-05（備份分類） |
| 狀態 | 歷史 **FAIL 保留**；不得抹除或降級為 PASS |

### Stage E.2 Remediation 追加（2026-11-28；非 Independent CR）

| Finding | 文件修正自檢 | 說明 |
|---|---|---|
| TR-CR-01／F-01 | 已修正 VP-TR-004 分層＋Workflow §4；含 Skip／XFail **原因**要求；**Runtime 仍 PENDING** | 自檢 ≠ 複審；不得因文件修正宣稱 VP-TR-004 PASS |
| TR-CR-02 | 已統一測資三層於 AGENTS／Integrity／Workflow／README／Rules | 未改 Private Fixture Gate／測試程式 |
| TR-CR-03 | 已載明 Owner 方案 A 與 §2.9.1 八步順序；**不降低**必要 Regression 門檻 | 本輪仍無 Commit／Runtime 授權 |
| TR-CR-04 | 已依 SPEC 修正 README CASH Two-Pass | 未改演算法；不重開 PR #12／#13 |
| TR-CR-05 | 已區分工程 Backup Root／Temp／`data/backups`／`data/uat`／`output/uat_*` | 未搬移／刪除私人備份實體 |

### Stage E.3 Independent CR（局部複審；2026-11-28）

| 欄位 | 內容 |
|---|---|
| 審查 | Stage E.3 Independent CR（唯讀局部複審；對話紀錄） |
| 分支 | `docs/adopt-governance-1.1` @ `0c0a65d2…`（WC 未 Commit；＝`master`） |
| 結論 | **PASS WITH NOTES** |
| Findings 閉環 | TR-CR-01～05、F-01 之**文件語意**均 **PASS**（詳見下表） |
| Notes | Runtime／VP-TR-001～007 仍 **PENDING**（設計如此；文件修正 ≠ Runtime PASS）；`tdd-rule.mdc` CRLF 警告非阻擋 |
| 狀態 | 追加於歷史 FAIL／E.2 之上；**未**抹除或降級 Stage E **FAIL** |

| Finding | Stage E | E.3 | 關鍵證據（摘要） |
|---|---|---|---|
| TR-CR-01 | FAIL | **PASS** | Pending VP-TR-004 A–D 分層；Exit 0≠全過；skip→需求 PENDING；須記 Passed／Failed／Skipped／XFailed／XPassed＋原因 |
| F-01 | FAIL | **PASS** | Workflow §4；Integrity；與 TR-CR-01 同源已關閉 |
| TR-CR-02 | FAIL | **PASS** | Workflow §2.2.1；Integrity；AGENTS；README；Rules；Gate／tests **未改** |
| TR-CR-03 | PENDING | **PASS** | Workflow §2.9.1：方案 A、不降門檻、不採文件-only 豁免、八步順序 |
| TR-CR-04 | FAIL | **PASS** | README ↔ SPEC Two-Pass／Pass1／Pass2／`SAME_DAY_RECONCILED`；演算法未改 |
| TR-CR-05 | PENDING | **PASS** | Backup Policy：工程 Backup／Temp ≠ `data/backups` ≠ `data/uat` ≠ `output/uat_*` |

Owner 已接受 E.3 結論；授權進入 Stage E.4 Commit 與 Stage F.1–F.3 隔離 Regression（不含 Push／PR／Merge／Tag；不含 Migration／正式 DB）。

### Stage E.4＋F.1–F.3／E.5／E.6 結案追加（2026-11-28；紀錄性；非 Independent CR）

| 欄位 | 內容 |
|---|---|
| Acceptance Commit | `4019528a84ff93d432550266b22c947291664c61` |
| Merge Commit | `8ee850bcc84afe62ccb6ae191b60605f2da784fd`（PR [#14](https://github.com/poyu88/trading_report/pull/14) MERGED） |
| 本機隔離 | Clean Clone；`uv sync --locked --dev` Exit 0；`ruff check .` Exit 0；`pytest -ra` → **299 passed／4 skipped／0 failed／0 xfailed／0 xpassed**（Exit 0） |
| 歷史哨兵 FAIL | 誤設 `TRADING_DB_PATH` 時 Alembic env 覆寫 Config URL → 1 FAIL；**保留**（EV-TR-GOV-E4F-SENTINEL-FAIL）；正式重跑未設該變數後通過。**不**自行定義為產品 Bug；**未**改 `alembic/env.py` |
| PR CI | run [`46042047293`](https://github.com/poyu88/trading_report/actions/runs/46042047293)：**Job SUCCESS**（ruff／pytest）；命令見 workflow `uv run --locked ruff check .`／`uv run --locked pytest -q`；摘要 `299 passed, 4 skipped`；Head＝Acceptance。**未**另擷取遠端逐步 process Exit Code 數字（不以虛構 Exit Code 取代 Job SUCCESS） |
| master CI | run [`46042689924`](https://github.com/poyu88/trading_report/actions/runs/46042689924)：**Job SUCCESS**；同上命令；摘要 `299 passed, 4 skipped`；Head＝Merge |
| 本機程序 Exit Code | 隔離跑有直接記錄：sync／ruff／pytest 均 **Exit 0**（EV-TR-GOV-E4F-*） |
| 永久歸檔 | Evidence ID `EV-TR-GOV-E4F-*`；Stage E.6 建立 SHA256_MANIFEST；Stage E.7 來源↔目的 **再核對 ALL_MATCH**（不重複備份）；Temp／Clone **未刪** |
| 結案分支（Stage E.6 紀錄當時） | `docs/governance-1.1-closeout` 當時 **未 Commit／待授權**（**歷史狀態**；後續以實際結案 Commit／PR 為準） |

VP-TR 更新摘要見上表；**不得**因 Merge／CI SUCCESS 將 VP-TR-004 C／D 或 VP-TR-005～007 改為 PASS。

---

## 歷史資料／Golden 待驗證（PENDING_DATA；保留不覆寫）

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
| GOLD-004 | 本機全年 D 回歸 **PASS**（`necessary_ok`；HTML bridge＋正式 FIFO／Report；逐筆 Trace↔C；必要失敗→FAIL） | **原始 CSV Parser 尚未獨立驗收**（僅 bridge 後流程；不得宣稱 Parser 完整驗收）；無跨年期初限制仍列 known_limitations；Excel 逐欄未全面驗（見 summary `excel_verification_scope`） |

本機摘要：`data/golden/evidence/phase03_partial_cases_summary.json`、`phase03_gold004_summary.json`（gitignored）。

## 原始 capital CSV Parser 獨立驗收

| 欄位 | 內容 |
|---|---|
| CR ID | GOLD-CSV-PARSER |
| 問題名稱 | Phase 3 UAT 以 HTML bridge 匯入；不得宣稱 `parse_csv`／capital CSV profile 已獨立驗收 |
| 程式位置 | `scripts/_golden_phase3_cr10a_uat.py`；`scripts/_golden_phase3_gold004_uat.py`；`backend/ingest/csv_parser.py` |
| 目前行為 | 真實 CSV 列轉 HTML → `statement_html_v1` Import；來源 SHA 仍鎖定原始 CSV |
| 已驗證範圍 | 轉換後匯入／FIFO／Report／C↔D（001-2236、004） |
| 未驗證範圍 | 雙表頭 capital CSV 直接經正式 CSV Parser 端到端 |
| 缺少資料 | 無需新交易；待 capital_csv profile／skip 第二表頭列 |
| 資料齊全後 | 新增 profile＋直接 CSV Import 回歸；bridge 僅作相容路徑 |
| 未來驗收條件 | 原始 CSV Parser 路徑 PASS 且與 bridge 財務結果一致 |
| 重新啟動條件 | Owner 授權新增 CSV profile（非大型重構前提下） |
| 目前狀態 | PENDING_DATA |

## 延期（DEFERRED；本輪非阻擋）

| ID | 說明 | 狀態 |
|---|---|---|
| CR-10A GOLD-001-2236 | 逐筆 Trace↔C＋聚合＋故障注入本機 **PASS**；重複鍵多重集；Excel 未驗證範圍已記錄 | **本輪已驗（合併前收尾）** |
| CR-10B | 合法副本 → FAIL／非零 exit／failed_checks；觀測自正常 UAT（非固定 True） | **本輪已驗（合併前收尾）** |
| CR-10C | Conservation 實際守恆狀態＋audit `conservation_ok` 一致性；非法型別不得 PASS | **本輪已驗（合併前收尾）** |
| GOLD-CSV-PARSER | HTML bridge ≠ 原始 CSV Parser 完整驗收 | **PENDING_DATA**（見上節） |
| CR-06B／06C | 原始九筆 Excel／Trace／獨立 C 第一片段費用落點已驗；**非零利息真實樣本**仍缺 | 見 `PR12_ORIGINAL_CR_WRITEOFF.md`；占位 `test_cr06c_nonzero_interest_first_fragment_pending_data`（skip）；稽核見 `PR12_TEST_DATA_SOURCE_AUDIT.md` |
| 真實帳戶副本 UAT 重跑 | Round-4 checklist；完整帳戶一致性隔離 UAT | **PENDING_DATA**（環境／資料；非原始 CR 程式 OPEN） |
| Manifest Pydantic／mypy／Hypothesis／Mutation／完整稅務引擎 | 獨立評估 | DEFERRED |
