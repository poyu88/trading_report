# 真實交易黃金驗收 — Phase 0／1（R1.0）

> **狀態**：Phase 0／1 **基礎開發收尾**（待 Owner 確認進入 Phase 2）；**CR-10A 仍未結案**；Phase 2＋未授權。
> **本文件**：非敏感技術規範與公開摘要。**禁止**貼入真實交易明細、帳戶號碼、完整交叉核對列。

## 0. Phase 0／1 收斂摘要

### 已結案

| ID | 說明 |
|---|---|
| GOLD-CR-01 | 日期真實排序 |
| GOLD-CR-03 | DB／WAL／SHM 指紋前後比 |
| GOLD-CR-04 | 實際 `git ls-files`＋returncode |
| GOLD-CR-06 | 非法 Decimal／非有限／JSON 可序列化錯誤鍵 |
| GOLD-CR-07 | 千分位先驗證 |
| GOLD-CR-08 | SHA256 鎖定與 blocker |
| GOLD-CR-09 | 失敗非零結束碼 |
| GOLD-CR-10 | 列合法性；**invalid／excluded 分計**；非法列阻擋完整 PASS |
| INV-01～05 | 盤點骨架（本機 evidence） |

### 已實作、完整真實資料驗收仍 PENDING_DATA

| ID | 說明 |
|---|---|
| GOLD-CR-02 | 獨立 Reviewer 本機覆核 |
| GOLD-CR-05 | 外部 trade id／列指紋（可立即核對欄已實作） |
| GOLD-CR-11 | 多帳戶真實樣本（歧義偵測已實作） |
| GOLD-ESUN-OPENING | 玉山缺買進／期初 |
| GOLD-SPECIAL-INSTRUMENT | 特殊商品真實樣本 |
| GOLD-FIN-EDGE | 真實逐筆財務邊界 |

### 延期（DEFERRED）

CR-10A／10B／10C；Manifest Pydantic／mypy／Hypothesis／Mutation／完整稅務引擎。

### 剩餘風險

- 獨立 C（Phase 2）未建；不得以 B／受測 D 反推答案。
- HTML-xls／玉山路徑尚未套用與 capital CSV 同等之 invalid 分計（已標記 limitation）。
- 正式 DB／真實 Manifest 僅本機；公開 Git 無真實明細。

## 1. 授權與停止條件

| 項目 | 本輪 |
|---|---|
| Phase 0 INV-01～05 | 已完成（本機 evidence） |
| Phase 1 Manifest／索引／布局 | 已完成（本機 `data/golden/`，gitignored） |
| Phase 2 獨立 C | **未授權**（待 Owner 確認） |
| Commit／Push（非敏感碼與文件） | 依 Owner 授權執行；≠ 獨立審查通過 |
| Merge／正式 Migration／寫入正式 DB | **禁止** |

## 2. 四層架構（A／B／C／D）

| 層 | 含義 | Phase 1 |
|---|---|---|
| **A** | 原始來源（CSV／HTML-xls／XLSX） | 指紋＋Manifest 鎖定 |
| **B** | 舊版報表／已知偏差索引 | `baseline_b`（非答案） |
| **C** | 獨立標準答案（A＋SPEC／Decimal） | **目錄保留未驗收** |
| **D** | 新版執行輸出 | 後續 |

停止以平均拆分總額、人工虛假多列、舊版錯誤 DRAFT 作為財務正向依據。

## 3. INV-01～05 修正結果（公開）

| ID | 結果 |
|---|---|
| **INV-01** | Manifest／evidence 必須完整 **64** 字元 SHA256；盤點前／後比對；漂移＝阻礙 |
| **INV-02** | 分列 physical／header／valid／excluded／duplicate／per-symbol／DB imported；**禁約數** |
| **INV-03** | CSV↔DB 逐欄交叉；缺欄標 `UNKNOWN`／`NOT_IN_SOURCE`／`NOT_IN_SCHEMA`，不補造 |
| **INV-04** | 可重用 `verify_detail_xlsx_finance` **骨架**；不得當可信答案；不得用受測輸出反推 C |
| **INV-05** | 故障反例須 **同向**：`cost+1` 且 `income+1`，或 `cost-1` 且 `income-1`（profit 不變）。廢止反向 `∓` |

## 4. Decimal 正規化（匿名）

交叉核對金額／單價時使用 `backend.util.decimal_text.normalize_decimal_text`：

- 去千分位；`Decimal` 解析；去掉尾隨 `0`（例：`1105.00` → `1105`）。
- 匿名測試：`tests/test_decimal_text_normalize.py`。
- **不得**在公開 PR 貼出真實 72 筆正規化前後明細。

## 5. Manifest 必要欄位

見模板：[`golden_manifest.template.json`](./golden_manifest.template.json)。

必要欄位：`case_id`, `source_path`, `source_format`, `source_sha256`（64）, `file_size_bytes`, `broker`, `account_alias`（去識別）, `parser_profile`, `parser_version`, `date_from`, `date_to`, `physical_row_count`, `valid_trade_count`, `excluded_row_count`, `invalid_row_count`, `duplicate_row_count`, `symbol_count`, `contains_2236`, `source_role`, `validation_status`, `known_limitations`。

`invalid_row_count`（非法必要交易列）與 `excluded_row_count`（總合等正常排除）**必須分開**；有非法列時不得宣告完整驗收成功。

## 6. 本機布局（不進公開 Git）

```text
data/golden/
  manifest/ source_a/ baseline_b/ expected_c/ runs_d/ mutations/ evidence/
```

- `.gitignore` 已排除整個 `data/`、`input/`、`output/`、`*.db`、`*.xls`／`*.xlsx`。
- 真實 Manifest、交叉核對全文、Reviewer ZIP **僅本機**。

## 7. 盤點工具

- `scripts/_golden_phase01_inventory.py`：唯讀盤點（URI `mode=ro`）；**禁止** `init_db`／`apply_import`／migration／寫入正式 DB。
- 公開可報告：通過／失敗摘要、相對路徑、非敏感計數結構說明。
- 禁止報告：逐筆價量、淨收付明細、帳戶識別資訊。

## 8. 公開計數結構說明（無明細）

| case | 結構結論（無逐筆） |
|---|---|
| GOLD-001 | 年度 CSV；含 2236；與對應 `file_sha256` batch 交叉 PASS |
| GOLD-002 | HTML-xls；valid／symbol 已重核（廢止未驗證約數） |
| GOLD-003 | 玉山 XLSX；2236 **缺買進**；不與群益混配；不自造期初 |
| GOLD-004 | 四年度 CSV valid 合計對應 DB trades 總計；**不得**把 DB 總筆數當 CSV 實體列總和 |

精確數字與完整 SHA256 見本機 `data/golden/evidence/phase01_summary.json`（gitignored）。

## 9. 完整性禁令

禁止：假性驗收、檔案存在冒充財務、未知當成功、平均拆總額、非空白列當有效交易、受測輸出反推 C、擅自改黃金資料、捏造 RED／GREEN、隱瞞失敗、改正式 DB、降低標準求表面成功。
