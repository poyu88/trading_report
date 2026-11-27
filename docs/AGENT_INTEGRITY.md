# Agent Integrity（驗收誠信唯一正式來源）

本文件是 **trading_report** 專案 **Agent／開發者驗收誠信與 anti-gaming** 的唯一正式來源。
流程細節見 [`DEVELOPMENT_WORKFLOW.md`](DEVELOPMENT_WORKFLOW.md)；TDD 方法見 [`test/TDD.md`](test/TDD.md)；待驗證登記見 [`test/PENDING_DATA_VALIDATION.md`](test/PENDING_DATA_VALIDATION.md)。
本檔不取代 Code Review 的 `PASS`／`PASS WITH NOTES`／`FAIL` 三態結論。

| 來源 | 值 |
|---|---|
| 工程制度來源 | `python-engineering-template` tag `v1.1.0`／standards `1.1.0-template` |
| 來源 Commit SHA | `9bb9cb2a8bb4689533c4b1a3cbf517f2af1fb704` |
| 產品契約 | 仍以 PRD／SPEC／Golden／UAT 裁決器為準；本檔**不**覆蓋財務契約 |

---

## 0. 強制分層：文件 ≠ 自動化已完成

| 層級 | 意義 | 本專案例子 |
|---|---|---|
| **POLICY** | 文件要求；靠 Agent 指令與 Independent CR | TDD 紀律、禁虛構證據、禁弱化財務斷言 |
| **ENFORCED (tool)** | 成熟工具強制；各工具自身 exit code | `uv`、`ruff check`、`pytest`、CI `lint`／`pytest` Jobs |
| **ADVISORY** | 輔助警示；非正式唯一依據 | （若日後採用）Cursor 敏感 Hooks 等 |
| **NOT_ADOPTED** | 尚未採用之工具（採用資訊，**非**驗收四態） | Mypy、Coverage 門檻、Ruff Format CI、母版 Hooks |
| **DEFERRED** | 未自動化／未成熟；另案授權 | Mutation、完整稅務引擎等（見 Pending／歷史 DEFERRED） |

**禁止**將政策文件存在視為自動化機制已完成。
**禁止**為讓 CR PASS 而製造替代假驗證、降低已採用工具門檻或刪除有價值測試。
**禁止**為完成 TODO 強行實作 DEFERRED／NOT_ADOPTED 項（須 Owner 授權）。

---

## 1. Anti-overengineering 永久原則

優先採用成熟、可驗證的既有工具及參考實作。

當需求、資料、測試契約或參考案例不足時，應明確記錄限制並列入 [`test/PENDING_DATA_VALIDATION.md`](test/PENDING_DATA_VALIDATION.md)。

不得為滿足規格完整性而強行實作不成熟的驗證機制。
不得進行缺乏實際需求的過度抽象化、過度工程化及形式化驗收。
不得為完成 TODO 而製造假性 PASS。
未經 Owner 授權，不得擅自啟動 DEFERRED 項目或強制新增品質工具。

---

## 2. 工程驗收四態（唯一正式狀態模型）

工程驗收層個別檢查結果**僅**可使用：

`PASS`｜`FAIL`｜`PENDING`｜`N/A`

| 狀態 | 意義 | 何時使用 |
|---|---|---|
| `PASS` | 已依既定規則、預期結果與可信證據實際驗證且通過 | 規則、資料、環境、權限齊備，且執行證據支持通過 |
| `FAIL` | 已實際驗證且未通過 | 規則明確、已執行驗證，並取得**不符合**要求的證據；不得降級／抹除／覆寫為 PASS／PENDING／N/A |
| `PENDING` | 尚未完成可信驗證 | **僅**在缺規則、預期結果、可信資料、環境、權限，或無法取得有效驗證結果時使用 |
| `N/A` | 該驗收項確定不適用 | 必須附書面依據；不得用來排除仍屬必要的檢查 |

**FAIL vs PENDING（強制）**：規則明確且已執行並有不符合證據 → **`FAIL`**。缺必要條件以致無法有效驗證 → **`PENDING`**。不得以 PENDING 掩蓋已證實的不符合。

### 2.1 未完成語意 → 工程層歸 PENDING

| 原用語（非工程四態） | 工程驗收層 |
|---|---|
| `NOT_RUN`／`SKIPPED`／`BLOCKED` 等未完成情境 | `PENDING` |
| 歷史 `PENDING_DATA`（缺資料／環境／授權） | `PENDING`（保留原文作為 Evidence 用語） |
| 缺規則／缺預期結果／缺資料／缺環境／缺授權 | `PENDING` |

**保留**工具原生輸出、CR 三態、歷史 Class C 證據原文、既有 `PENDING_DATA` 欄位用語；**禁止**全 Repository 盲目字串替換。

### 2.2 有效驗證要件（缺一不可則不得 PASS）

宣稱 `PASS` 前必須同時具備：

1. 明確驗證規則與適用範圍
2. 可檢查的預期結果
3. 可信資料或輸入（非虛構）
4. 適當執行環境與必要權限
5. 可獨立審查的真實執行證據（命令、exit code、輸出摘要或同等物）

任一要件不足 → 記 **`PENDING`**，並填寫 Reason、Evidence（現有限度）、Next Action、重新驗證條件。
**禁止**虛構驗證規則、資料、預期結果或 PASS。

### 2.2.1 獨立預期結果（Independent Expected Result）

- **禁止**以待測系統（SUT）自身輸出作為**唯一**預期結果，形成循環驗證。
- 預期結果須有適當且可追溯的獨立依據，例如：已核准 PRD／SPEC、可獨立推導的財務／FIFO 規則、經確認的參考資料、獨立計算結果、經驗證的 Golden Case。
- 若無可信依據 → 該項列 **`PENDING`**；**禁止**為取得 PASS 而事後調整預期結果。

### 2.2.2 測資與驗收邊界（合成／私人／正式）

與 Workflow §2.2.1 一致，分三層：

| 層 | 允許 | 禁止／限制 |
|---|---|---|
| 日常 TDD／公開 CI | 清楚標記的合成資料、公開安全 Fixture、`tmp_path` 等隔離測資 | 載入私人交易資料；讀寫正式 DB |
| 私人資料驗收 | **經 Owner 授權**之 REAL_DERIVED、Golden 或其他可信私人測資，於隔離環境自動化驗收 | 須符合既有 **Private Fixture Gate**、gitignore／敏感保護、最小必要資料、隔離 DB／輸出、獨立預期結果；**不上傳**公開 Git／CI；錯誤訊息**不洩漏**私人財務數值 |
| 正式資料 | （非一般自動化測試目標） | 未授權讀取／修改／複製正式交易 DB、正式報表、原始對帳單；作為一般自動化測試可寫入目標 |

- **禁止**將合成資料冒充真實資料、REAL_DERIVED、Golden 或正式 UAT 證據。
- 合成測試通過 **不代表** 真實資料業務驗收已完成；缺少必要私人測資 → 對應需求維持 **`PENDING`**。
- **禁止**虛構驗收規則或測資以消除 PENDING。
- **不得**在本治理修正中擅自修改既有 Private Fixture Gate 或產品測試程式。

### 2.3 工具採用狀態（不是驗收四態）

| 採用資訊 | 意義 |
|---|---|
| `NOT_ADOPTED` | 本專案尚未採用該工具／檢查；屬採用資訊，**不是** `PASS`／`FAIL`／`PENDING`／`N/A` 之一 |

- **不得**將 `NOT_ADOPTED` 直接等同 `N/A`。
- 工具是否採用仍待評估 → 評估事項列 **`PENDING`**（見 Pending 檔）。
- 僅「確定不適用的驗收項」才用 `N/A` 並附依據。
- 不得因未採用而變更既有品質門檻，或未經授權強制新增工具。

本專案目前 **NOT_ADOPTED**：Mypy、Coverage 門檻、Ruff Format CI、母版敏感 Hooks（詳見 [`STANDARDS_VERSION.md`](../STANDARDS_VERSION.md)）。

### 2.4 與其他狀態空間的邊界

| 空間 | 合法值（摘要） | 不得混用為 |
|---|---|---|
| 工程驗收四態 | PASS／FAIL／PENDING／N/A | CR 結論；工具採用 |
| Code Review | PASS／PASS WITH NOTES／FAIL | 工程驗收四態 |
| 產品 Pending 歷史用語 | PENDING_DATA／CLOSED／DEFERRED 等 | 不得抹除史實；工程層對應見 §2.1 |
| 產品 UAT／Golden 裁決器 | 既有產品結論語意 | 不得改寫為製造工程 Overall PASS |
| 工具原生 exit／輸出 | 各工具自身語意 | 不得改寫以製造 PASS |

### 2.5 禁止 Overall 聚合器；Pytest 分層

本專案**不**提供、**不**新建工程 Overall PASS 聚合器。已採用成熟工具須**逐項**記錄（Command、Exit Code、輸出摘要／原生計數）：

```powershell
uv sync --locked --dev
uv run --locked ruff check .
uv run --locked pytest -q
```

Pytest／測試相關工程狀態必須區分：

1. **工具執行成功**（程序 Exit Code 語意）
2. **個別測試案例通過**（Passed 等）
3. **需求驗收通過**（對應 PRD／SPEC／Pending）
4. **真實資料業務驗收通過**（授權私人／Golden／UAT）

強制：

- 記錄適用之 Passed／Failed／Skipped／XFailed／XPassed 與 Exit Code；Skipped／XFailed 須附原因。
- Exit Code `0` **≠** 所有案例及需求已通過。
- 缺私人測資而跳過 → 對應需求 **`PENDING`**；已證實不符合 → **`FAIL`**。
- **禁止**以工具成功、CI 綠燈或測試數量替代個別需求驗收（見 `VP-TR-004`）。

- CI 以 [`.github/workflows/pytest.yml`](../.github/workflows/pytest.yml) 為準（目前 `lint`∥`pytest`）。
- **不得**因母版列出 format／mypy／coverage，即宣稱本產品已強制採用或已驗收該等工具。

> 此處是工程驗收狀態，不是 CR 結論三態。

---

## 3. 禁止的規避行為（Anti-gaming）

禁止：

1. 以固定 `True`／空實作取代實際驗證契約。
2. 以表面條件（僅檔案存在、空成功、關鍵字出現／消失）冒充語意正確性（除非契約本身即為該條件）。
3. 偽造 PASS、測試／CI／UAT 結果或 TDD 歷史。
4. 用 Mock／Stub 隱藏必要負向案例。
5. 刪除、`skip`、`xfail` 或弱化必要測試（尤其財務斷言）換綠燈。
6. 擅自降低已採用之 Lint／測試門檻；或擅自新增工具門檻冒充已完成採用。
7. 全域 ignore、過寬 ignores、無理由 `noqa`。
8. 捕捉例外後回傳成功。
9. 改 CI 選取範圍或驗收函式逃避 CR。
10. 將未驗證項目標記完成，或將 `PENDING` 靜默改為 `PASS`／`N/A`；或以 `PENDING` 掩蓋已證實的 `FAIL`。
11. 新建 Overall PASS 聚合器而不經 Owner 授權與獨立驗證。
12. 改寫歷史 FAIL、工具原生執行證據，或盲目全庫替換狀態字串。
13. 以 SUT 輸出作為唯一預期（循環驗證），或將合成測試冒充真實資料／Golden／正式 UAT 驗收。
14. 以實作自檢冒充 Independent CR。

違規：CR **FAIL**、阻擋 Merge、RCA、補回歸、重新獨立 CR。實作 Agent 不得自行解除阻擋。

---

## 4. 輔助檢查 vs 正式驗收

| 類型 | 例子 | 語意 |
|---|---|---|
| 正式必要（已採用 L1） | `ruff check`、`pytest`、CI 對應 Jobs | 各記工具執行狀態；pytest 另須案例／需求分層；工具失敗 → `FAIL`；未跑／不明 → `PENDING` |
| 未採用 | Mypy、Coverage 門檻、Ruff Format CI、母版 Hooks | `NOT_ADOPTED`；評估中則另列 `PENDING`；**不得**標 `N/A` 了事 |
| 產品業務驗收 | Golden／REAL_DERIVED／FIFO UAT／財務欄位契約 | 產品裁決器與 SPEC；合成通過 ≠ 真實資料業務驗收完成 |

---

## 5. 已知待驗證與限制

見 [`test/PENDING_DATA_VALIDATION.md`](test/PENDING_DATA_VALIDATION.md) 與 [`STANDARDS_VERSION.md`](../STANDARDS_VERSION.md)。
Anti-gaming 目前主要依靠：**本文件（POLICY）＋已採用成熟工具（ENFORCED）＋Independent CR＋產品 UAT／Golden 契約**。
