# BUGBOT 全域審查規範

> 本檔為審查輔助摘要，**不是**第二套開發權威。
>
> 本專案僅使用根目錄本檔；無 `frontend/`，亦無 `backend/.cursor/BUGBOT.md`。
>
> 權威來源：[`docs/DEVELOPMENT_WORKFLOW.md`](../docs/DEVELOPMENT_WORKFLOW.md)、[`docs/CODING_STANDARDS.md`](../docs/CODING_STANDARDS.md)、[`.cursor/rules/commit-rule.mdc`](rules/commit-rule.mdc)。

---

## 嚴重問題（必須修正，否則不得合併）

### 空的錯誤處理 [quality]

禁止空的 `except:`／靜默 `pass`。保留上下文或明確降級；細節見 [`docs/CODING_STANDARDS.md`](../docs/CODING_STANDARDS.md) §5。

```python
# 禁止
try:
    risky_operation()
except:
    pass

# 正確：記錄或轉換為明確例外
try:
    risky_operation()
except ValueError as e:
    logger.error("處理失敗：%s", e)
    raise
```

---

## 重要問題（強烈建議修正）

### 語言規範 [i18n]

**必須使用繁體中文**用於：使用者可見錯誤訊息、解釋「為什麼」的註解、commit 描述、專案文件。

**可使用英文**用於：識別子名稱、技術術語。

```python
# 使用者可見訊息請用繁中
raise ValueError("輸入格式錯誤：請提供有效路徑")
```

---

## 建議改善

### Git Commit Message 格式 [git]

完整規範以 [`.cursor/rules/commit-rule.mdc`](rules/commit-rule.mdc) 為唯一權威（勿在本檔平行維護第二套）。

摘要：`英文類別：繁體中文描述`；類別僅 `add`／`fix`／`restruct`／`test`／`doc`。

---

## 問題標籤說明

- `[security]`：安全性問題，最高優先級
- `[quality]`：程式碼品質問題
- `[tooling]`：工具鏈與環境設定
- `[api]`：API 設計與規範
- `[i18n]`：國際化／語言相關
- `[git]`：版本控制規範
- `[style]`：程式碼風格與命名（以 Coding Standards 為準）
