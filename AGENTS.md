# AGENTS.md — 所有 Agent 的共同入口

本檔是跨 Agent 的**精簡入口**，不是第二套完整規範。細節以各唯一權威來源為準。

工程治理採用：`python-engineering-template` tag **`v1.1.0`**／standards **`1.1.0-template`**（來源 SHA 見 [`STANDARDS_VERSION.md`](STANDARDS_VERSION.md)）。

## 開發前必讀

依任務至少閱讀：

| 需求 | 權威文件 |
|---|---|
| 流程／權限／CR／UAT／Merge／隔離 | [`docs/DEVELOPMENT_WORKFLOW.md`](docs/DEVELOPMENT_WORKFLOW.md) |
| 風格／Docstring／Ruff | [`docs/CODING_STANDARDS.md`](docs/CODING_STANDARDS.md) |
| TDD 方法 | [`docs/test/TDD.md`](docs/test/TDD.md) |
| 驗收誠信／四態／anti-gaming | [`docs/AGENT_INTEGRITY.md`](docs/AGENT_INTEGRITY.md) |
| 待驗證登記（產品沿用擴充） | [`docs/test/PENDING_DATA_VALIDATION.md`](docs/test/PENDING_DATA_VALIDATION.md) |
| 備份／產物分類 | [`docs/BACKUP_AND_ARTIFACT_POLICY.md`](docs/BACKUP_AND_ARTIFACT_POLICY.md) |
| 產品需求 | [`docs/prd/PRD.md`](docs/prd/PRD.md) |
| 技術／財務契約（含 FIFO／SQLite／報表） | [`docs/spec/SPEC.md`](docs/spec/SPEC.md) |
| 工具與依賴 | `pyproject.toml`／`uv.lock` |
| CI 實際行為 | [`.github/workflows/pytest.yml`](.github/workflows/pytest.yml) |
| 規範版本／採用矩陣 | [`STANDARDS_VERSION.md`](STANDARDS_VERSION.md) |

Cursor Rules（`.cursor/rules/*.mdc`）僅為精簡指針。

## 核心禁止事項（強制）

1. **禁止**虛構測試結果、RED／GREEN 歷史、CI／UAT／驗收證據，或虛構驗證規則／預期結果／PASS。
2. **禁止**弱化測試斷言（尤其財務）、刪除／skip／xfail 必要驗證，或擅自降低已採用品質門檻。
3. **禁止**未經 Owner 明確授權執行 Commit、Push、建立／合併 PR、Merge、Tag。
4. **禁止** Force Push 或改寫遠端 Git 歷史（**無例外**；Agent 永不執行）。
5. **禁止**在規範衝突時自行選擇較寬鬆的規則；必須回報並以較嚴格／權威文件為準；衝突未決時工程驗收標 `PENDING`。
6. **測資三層**（細節見 Workflow §2.2.1／Integrity）：日常 TDD／公開 CI 僅合成或公開安全 fixture；經 Owner 授權之私人／Golden 隔離驗收須符合 Private Fixture Gate 且不上傳公開 Git／CI；**禁止**未授權讀寫正式 `data/trading.db`／正式報表／原始對帳單，或將其作為一般自動化測試可寫入目標。
7. **禁止**為滿足規格完整性而強行實作缺乏需求／契約／案例的驗證機制，或製造假性 PASS；**禁止**以 Pytest exit 0／CI 綠燈／測試數量替代個別需求驗收。
8. **禁止**擅自將 `NOT_ADOPTED` 工具（Mypy／Coverage／Ruff Format CI／母版 Hooks）當作已採用或已驗收。
9. **禁止**擅自建立其他工程永久備份根；產品 `data/backups` ≠ 第二 Backup Root（見 Backup Policy）。
10. **禁止**以自我檢查冒充 Independent CR；禁止新建 Overall PASS 聚合器；禁止盲目全庫替換狀態字串。
11. **禁止**覆蓋產品專屬契約（PRD／SPEC／FIFO／Golden／UAT 裁決器）或以母版通用內容削弱之。
12. 缺規則／資料／環境／權限時標 `PENDING` 並登記 [`docs/test/PENDING_DATA_VALIDATION.md`](docs/test/PENDING_DATA_VALIDATION.md)；不停止其他可完成工作。

## 衝突處理

| 衝突類型 | 以誰為準 |
|---|---|
| Rule vs Workflow | `docs/DEVELOPMENT_WORKFLOW.md` |
| Rule vs Coding Standards | `docs/CODING_STANDARDS.md` |
| Rule vs TDD.md | `docs/test/TDD.md` |
| 文件表格 vs CI YAML | `.github/workflows/pytest.yml` |
| 依賴清單 | `pyproject.toml`／`uv.lock` |
| 誠信／工程驗收四態 | `docs/AGENT_INTEGRITY.md` |
| 待驗證事項 | `docs/test/PENDING_DATA_VALIDATION.md` |
| 財務／FIFO／報表契約 | `docs/spec/SPEC.md`（需求面輔以 PRD） |
| 規範版本／工具採用 | `STANDARDS_VERSION.md` |

發現不一致：回報衝突，工程驗收層標 **`PENDING`**，不得靜默採寬鬆解釋。

## 工程驗收四態（摘要）

僅：`PASS`｜`FAIL`｜`PENDING`｜`N/A`。細節與映射見 Integrity。
工具採用 `NOT_ADOPTED` **不是**四態之一，不得直接等同 `N/A`。

## Executable Quality Controls（已採用）

本機與 CI 共用同一組**已採用**成熟工具必要檢查（各自獨立執行與記錄 exit code；**無**自訂 Overall PASS 聚合器）：

```powershell
uv sync --locked --dev
uv run --locked ruff check .
uv run --locked pytest -q
```

- Ruff lint：`ruff check`（CI `lint` Job）
- pytest（CI `pytest` Job）：須記錄 Exit Code 與 Passed／Failed／Skipped／XFailed／XPassed（適用時）
- 工具執行成功 ≠ 個別案例通過 ≠ 需求驗收通過 ≠ 真實資料業務驗收通過（見 Workflow §4、`VP-TR-004`）
- 正式 Regression 應在獨立驗收環境執行，避免含正式交易資料之工作目錄（見 Workflow §2.9.1）
- **NOT_ADOPTED（本輪）**：Mypy、Coverage 門檻、Ruff Format CI、母版敏感 Hooks — 見 [`STANDARDS_VERSION.md`](STANDARDS_VERSION.md)
