---
description: "多視角交叉驗證 — 並行 Agent 合成共識報告"
allowed-tools: Read, Bash, Grep, Glob, Task, Write, mcp__sequential-thinking__sequentialthinking
argument-hint: "[spec_path] [files... | git-diff-range | latest]"
---

# /cross-validate — 多視角交叉驗證

> 多個 Agent 並行分析同一組變更，Orchestrator 交叉比對後合成共識報告。

## 環境資訊
- 當前分支: !`git branch --show-current 2>/dev/null || echo "(未初始化)"`

## 輸入
驗證目標：$ARGUMENTS

## 參數解析

| Target 輸入 | 行為 |
|------------|------|
| `latest` / 無參數 | `git diff HEAD~1` |
| `HEAD~N..HEAD` | 指定 diff 範圍 |
| `main` | `git diff main...HEAD` |
| `path/to/dir/` | 掃描目錄 |
| `file1 file2` | 指定檔案 |

Spec（可選）：提供 `dev/specs/.../` 則讀取 brief_spec + dev_spec 作為對照。

---

## Step 0：專案偵測

讀取 CLAUDE.md + 目錄結構，推斷：
1. 技術棧（後端/前端框架）
2. 目錄映射（backend_dirs / frontend_dirs / test_dirs）
3. 專案規範（coding style、repo rules）

偵測失敗 → 通用全端模式。

## 視角選擇（自動）

| 條件 | 啟用視角 |
|------|---------|
| 變更含後端檔案 | 後端架構 ✅ |
| 變更含前端檔案 | 前端一致性 ✅ |
| 變更含測試檔案 | 測試覆蓋 ✅ |
| 變更含任何實作碼 | 安全效能 ✅ + 測試覆蓋 ✅ |

最少 2 個視角，否則建議改用 `/verify` 或 `/code-review`。

---

## Agent 調度（同一 message 並行發出）

### 共用輸出格式

每個 finding：`### XV-{PREFIX}-{NNN}: {標題}`，含嚴重度(P0/P1/P2)、位置(file:line)、描述、證據、建議修正。最後附 `## 總結`。

### 四個視角

| 視角 | Agent | Finding 前綴 | 核心審查點 |
|------|-------|-------------|-----------|
| 後端架構 | general-purpose (sonnet) | XV-BE | DI 完整性、TX 邊界、分層架構、Error handling、API 契約 |
| 前端一致性 | general-purpose (sonnet) | XV-FE | 狀態管理 pattern、設計系統、API Client 用法、路由 |
| 測試覆蓋 | general-purpose (sonnet) | XV-TC | 關鍵路徑測試、edge case、mock 正確性、斷言品質 |
| 安全效能 | Explore (sonnet) | XV-SP | OWASP Top 10、N+1、敏感資料洩漏、Race condition、資源洩漏 |

每個 Agent 收到：tech_stack + coding_style + 對應檔案 diff + spec（若有）。

### 降級策略
Timeout 180s → retry 1x (opus) → 部分完成用已有結果 → 全失敗回退 Orchestrator 直接分析。至少 2 視角完成，否則標記 `[INCOMPLETE]`。

---

## Orchestrator 合成

### Step 1：統一清點
所有 findings 合併為一張表。

### Step 2：交叉比對
- **共識**：多 Agent 指出相同問題 → 信心高，嚴重度取最高
- **矛盾**：Agent 觀點衝突 → 標記待人工裁定，雙方並列
- **盲區**：某 Agent 未覆蓋的區域 → 標記潛在盲區

### Step 3：嚴重度彙整
`最終嚴重度 = max(各 Agent 給出)`。2+ Agent 共識→信心高；單一→中；矛盾→待裁定。

---

## 輸出

對話內摘要（P0/P1/P2 + 共識/矛盾/盲區計數）。
持久化 Markdown 寫入 `dev/reviews/xval-{YYYY-MM-DD}-{short-desc}.md`。

## 規則
- 純讀取，不修改原始碼
- 唯一寫入是 `dev/reviews/` 報告
- Agent 無法驗證的項目標記 ❓
