# Backup and Artifact Policy

本檔為 **trading_report** **備份與產物分類**的權威來源（精簡）。
本機實際絕對路徑僅記載於 Owner 本機設定與私人 `BACKUP_INDEX.md`；**不得**將私人絕對路徑硬編碼進本 Repository 通用文件。

流程／權限仍以 [`DEVELOPMENT_WORKFLOW.md`](DEVELOPMENT_WORKFLOW.md) 為準；誠信以 [`AGENT_INTEGRITY.md`](AGENT_INTEGRITY.md) 為準。
產品 SQLite 保全、Backup API、WAL 一致性及備份保留制度仍以現行 [`spec/SPEC.md`](spec/SPEC.md) 與產品契約為準。
制度來源：`python-engineering-template` `v1.1.0`／`1.1.0-template`（SHA `9bb9cb2a8bb4689533c4b1a3cbf517f2af1fb704`）。

---

## 1. 工程備份根（Owner 指定）

1. Owner 指定**唯一永久工程 Backup Root**（永久保存 CR／證據／封存等）。
2. Owner 指定**唯一暫存 Temp Root**（隔離環境、可重建工作副本、暫存產物）。
3. 本專案使用專案名稱 `trading_report` 作為下一層子目錄。
4. **禁止** Agent 擅自建立其他永久工程 Backup Root。

## 1.1 產品路徑分類（≠ 第二工程 Backup Root）

下列為**產品作業／驗收路徑**，與「工程永久 Backup Root」分層；**不得**把產品 SQLite 作業備份誤稱為第二個工程永久 Backup Root，也**不得**直接將所有 SQLite 備份認定為可重建或可刪除資料。

| 路徑／類型 | 角色 | 說明 |
|---|---|---|
| Owner 工程 **Backup Root** | 永久工程備份 | CR／RCA／驗收證據／Manifest／經授權封存；私人 INDEX 管理 |
| Owner 工程 **Temp Root** | 暫存／可重建 | Clean Clone、隔離環境工作樹、cache、可重生環境 |
| `data/backups/` | **產品 SQLite 作業備份** | CLI／Backup API 產出之作業備份；保全語意依 SPEC；**不是**工程 Backup Root；**不得**預設視為可刪 |
| `data/uat/` 或 `data/uat_*.db` | 隔離 SQLite 副本 | UAT／驗收用；非正式 DB；可否刪除依 Owner／任務，非自動可丟 |
| `output/uat_*` | UAT 產出 | Excel／audit／exceptions／配對與守恆等；可重建性視任務，歷史證據另有歸檔規則時從其規定 |
| `data/trading.db` 等正式 DB | 正式資料 | **禁止**未授權讀寫；非一般自動化測試目標 |

## 2. 永久 vs 可重建（工程層）

| 永久保存（工程 Backup Root／指定封存） | 通常不作為工程永久備份 |
|---|---|
| CR／RCA 報告、驗收證據、SHA-256 Manifest、Evidence ID Map、被移出之實驗程式 | Clean Copy 整樹、mutation 工作副本、`.venv`、cache、可重生環境 |
| 經授權封存之真實對帳單／Golden 私人證據（**不得**入 Git） | 僅任務需要之暫存 Temp 產物 |

原則：

- **一個專案只有一個永久工程 Backup Root。**
- **產品 `data/backups` 不構成第二個工程 Backup Root**，但其內容可能具資料保全價值，刪除／搬移須依 SPEC／Owner 授權。
- **已有相同 SHA-256 的資料，不重複備份。**
- **歷史證據永久保留；可重新生成的環境不永久保存。**
- **任何搬移與刪除，必須有路徑對照及 Owner 授權。**
- **禁止**搬移、刪除或重新分類既有私人備份實體檔案（除非 Owner 明確授權本任務）。

## 3. 命名與索引

- 子目錄建議：`YYYYMMDD_phase_action`。
- 既有歷史目錄**不強制改名**（避免路徑失效）；以私人 `BACKUP_INDEX.md` 記錄別名與對照。
- 每專案維護唯一 `BACKUP_INDEX.md`（Backup ID、Evidence ID、原路徑、Canonical 路徑、SHA、Retention、清理候選）。
- Evidence ID 沿用既有制度；不平行發明第二套。

## 4. 複製與完整性

1. 先複製，再逐檔（或逐樹）SHA-256 核對。
2. 內容完全一致 → INDEX 記錄對應，**不**重複複製。
3. 內容不同 → **保留各版本**，禁止覆寫。
4. **禁止**修改已歸檔之原始 CR／證據內容。
5. 刪除舊位置須**獨立授權**；預設只複製、不刪。
6. `git diff` 空**不代表**正式 DB 或私人備份內容完整性已驗證。

## 5. Git 與可移植性

- 私人備份、本機 Temp、真實對帳單、正式 DB、私人 Golden evidence、產品作業備份中的敏感內容 **不得**納入 Git Repository（與既有 `.gitignore`／Workflow 一致）。
- 正式文件以 Evidence ID／通用說明引用歷史；**不得**把私人絕對路徑寫進通用 Markdown。
- **禁止**為備份制度開發未經授權的自訂工具或自動化框架。
- **禁止**未授權讀寫正式 `data/trading.db` 或覆寫歷史 UAT 輸出。

## 6. Agent 禁令（摘要）

1. 不得自建第二永久工程 Backup Root。
2. 不得將 `data/backups` 誤當工程 Backup Root，也不得未授權刪除產品 SQLite 備份。
3. 不得未驗證即刪來源；不得搬移／刪除／重分類既有私人備份實體。
4. 不得以整理為由改寫歷史報告結論。
5. Commit／Push／清理權限仍分別授權。
6. 不得修改私人 Handoff 或備份索引（除非 Owner 明確授權本任務）。
