# Standards Version — trading_report

本檔記錄本產品採用之工程治理母版版本與專案例外。
**不得**宣稱已採用尚未實際移植的制度或工具。

| 欄位 | 值 |
|---|---|
| Product repository | `trading_report` |
| Adopted template | `python-engineering-template` |
| Adopted template tag | `v1.1.0`（annotated tag；遠端 `refs/tags/v1.1.0`） |
| Adopted standards version | `1.1.0-template` |
| Source commit SHA（核對取得） | `9bb9cb2a8bb4689533c4b1a3cbf517f2af1fb704` |
| Tag object（annotated） | `455ad9765d1dfa7c1691de874be18078e8d1729f` |
| Source remote | `https://github.com/poyu88/python-engineering-template.git` |
| Adoption date | `2026-11-28` |
| Adoption branch（本輪） | `docs/adopt-governance-1.1` |
| Product baseline（採用前 HEAD） | `0c0a65d2adc0362ccccf54cf7050750b702d3607`（`master`＝`origin/master`） |
| Acceptance Commit（已合入） | `4019528a84ff93d432550266b22c947291664c61` |
| Merge Commit／PR | `8ee850bcc84afe62ccb6ae191b60605f2da784fd`／[PR #14](https://github.com/poyu88/trading_report/pull/14) |
| Closeout branch | `docs/governance-1.1-closeout`（Stage E.6 紀錄當時：未 Commit／待授權；**歷史狀態**，見結案 PR） |
| Python baseline | **3.11** |

## 已採用規範（本輪實際移植）

| 規範 | 產品權威位置 | 備註 |
|---|---|---|
| 工程驗收四態 PASS／FAIL／PENDING／N/A | [`docs/AGENT_INTEGRITY.md`](docs/AGENT_INTEGRITY.md) | 語意對齊母版 1.1 |
| Verification Integrity／有效驗證要件 | 同上 | 含獨立預期結果、禁止循環驗證 |
| 合成測資與真實資料驗收分界 | 同上；產品 UAT 見 Workflow §2.8 | 不削弱既有 Golden／私人 Fixture Gate |
| 工具採用 `NOT_ADOPTED` ≠ 驗收 `N/A` | 同上 | 見下方未採用工具 |
| 風險導向 Isolated Verification | [`docs/DEVELOPMENT_WORKFLOW.md`](docs/DEVELOPMENT_WORKFLOW.md) §2.10 | 保留產品 UAT 路徑契約 |
| 待驗證持久化 | [`docs/test/PENDING_DATA_VALIDATION.md`](docs/test/PENDING_DATA_VALIDATION.md) | **沿用並擴充**；不新建 `VERIFICATION_PENDING.md` |
| Independent CR（角色分離） | Workflow §2.7；Integrity | 實作自檢 ≠ Independent CR |
| Single Source of Truth／權威表 | Workflow 文件表；[`AGENTS.md`](AGENTS.md) | Rules 僅精簡指針 |
| Standards Versioning | 本檔 | 追蹤母版 Tag／SHA |
| 備份與產物分類 | [`docs/BACKUP_AND_ARTIFACT_POLICY.md`](docs/BACKUP_AND_ARTIFACT_POLICY.md) | 通用政策；私人路徑不入 Git |
| Agent 入口 | [`AGENTS.md`](AGENTS.md) | 精簡入口，非第二套完整規範 |

## 產品專屬規範（保留；母版不得覆蓋）

- [`docs/prd/PRD.md`](docs/prd/PRD.md)、[`docs/spec/SPEC.md`](docs/spec/SPEC.md)
- FIFO Two-Pass 演算法契約
- SQLite 資料庫契約
- Golden Case 驗收規則與私人 Fixture Gate
- 真實交易資料驗收／財務報表欄位及數值契約
- 既有產品 UAT 裁決器與路徑慣例（`output/uat_*`、`data/uat/**`）
- 歷史 TDD／CR／RCA／UAT 證據（含已結案 PR #12／#13）
- [`docs/test/TDD.md`](docs/test/TDD.md)、[`docs/test/TDD_STATUS.md`](docs/test/TDD_STATUS.md)
- [`docs/CODING_STANDARDS.md`](docs/CODING_STANDARDS.md) 與現行 `pyproject.toml`／CI 門檻

## 品質工具採用狀態

| 工具／檢查 | 採用狀態 | 說明 |
|---|---|---|
| `uv` | **ADOPTED** | 唯一套件管理器 |
| Ruff lint（`ruff check`） | **ADOPTED** | 本機＋CI `lint` Job |
| Pytest | **ADOPTED** | 本機＋CI `pytest` Job |
| 既有 GitHub Actions CI | **ADOPTED** | `.github/workflows/pytest.yml`（lint∥pytest） |
| Mypy | **NOT_ADOPTED** | 本輪不移植；見專案例外 |
| Coverage 門檻 | **NOT_ADOPTED** | 本輪不移植；見專案例外 |
| Ruff Format CI（`ruff format --check`） | **NOT_ADOPTED** | 本輪不強制；Format 另案評估 |
| 母版敏感 Hooks／hooks runtime | **NOT_ADOPTED** | 產品未採用母版 hooks 程式；母版 VP-003 仍 PENDING |

`NOT_ADOPTED` **不是**工程驗收四態；不得直接等同 `N/A`。

## 專案例外

1. **不強制移植**母版 L1 中的 Mypy、Coverage 門檻、Ruff Format CI、Hooks（Owner D2／Stage D 授權邊界）。
2. **不修改** `pyproject.toml`、`uv.lock`、CI Workflow 或現行品質門檻（本輪）。
3. 待驗證登記**優先沿用** [`docs/test/PENDING_DATA_VALIDATION.md`](docs/test/PENDING_DATA_VALIDATION.md)，避免與母版 `VERIFICATION_PENDING.md` 重複文件。
4. 產品財務／FIFO／Golden／UAT 裁決器優於母版通用 UAT 範本；母版僅提供工程治理層語意。
5. 母版自身仍有 **VP-002-D**（Manifest 外部相容）與 **VP-003**（Hooks Cursor runtime）為 PENDING；**不得**冒稱本產品已完整驗證相關能力。

## 後續 PENDING（摘要；非第二份清單）

**逐項四態與證據以** [`docs/test/PENDING_DATA_VALIDATION.md`](docs/test/PENDING_DATA_VALIDATION.md) **「工程治理待驗證（VP-TR）」為唯一權威來源**；本節僅摘要，避免重複維護。

| 摘要 | 狀態（詳見 Pending） |
|---|---|
| VP-TR-001 獨立驗收環境 | **PASS**（已有隔離 Clean Clone 證據） |
| VP-TR-002 測試隔離安全 | **PASS**（範圍限定本輪 CI 等效 Regression） |
| VP-TR-003 Lockfile 一致性 | **PASS** |
| VP-TR-004 Pytest／需求驗收（分層） | **PENDING**（A 工具層本機／CI 已有通過證據；私人需求 C／真實 UAT D 仍 PENDING） |
| VP-TR-005 Migration 副本 | **PENDING**（另案） |
| VP-TR-006 正式 DB 升級授權 | **PENDING**（另案） |
| VP-TR-007 未採用工具評估 | **PENDING**／工具狀態見上方 `NOT_ADOPTED` |

不得因本檔摘要與 Pending 表並存而維護第二套待驗證清單。

## 來源核對備註

- 本機以 `git rev-parse "v1.1.0^{commit}"` 與 `git ls-remote --tags origin v1.1.0` 核對 Tag 指向 `9bb9cb2a…`。
- 母版該 Commit 內 `STANDARDS_VERSION.md` 仍記載「尚未建立 Tag」屬母版結案文件時點敘述；**實際 Git Tag `v1.1.0` 已存在並指向上述 SHA**。產品採用以 Git Tag／peeled commit 為準。
