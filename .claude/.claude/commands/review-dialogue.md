---
description: "雙 AI 對話式審查 — Claude 與 Codex 互審至共識"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Task
argument-hint: "<spec 目錄路徑 | latest> [spec|code|test] [resume]"
---

# /review-dialogue — 雙 AI 對話式審查

> Claude 提交 → Codex 審查 → Claude 驗證/防禦/修正 → 迭代至共識。
> Session 目錄規則見 `.claude/references/review-protocol.md`

## 環境資訊
- 當前分支: !`git branch --show-current`
- Codex: !`codex --version 2>/dev/null || echo "NOT FOUND"`

## 輸入
目標：$ARGUMENTS

---

## Scope（Dialogue 類別）

| Scope | SOP 階段 | 審查對象 | 修正對象 |
|-------|---------|---------|---------|
| `spec` | S2 | dev_spec + brief_spec | s1_dev_spec.md |
| `code` | S5 | git diff + changed files + DoD | 原始碼 |
| `test` | S6 | 測試結果 + 失敗 log | 原始碼 + 測試碼 |

**Scope 解析優先序**：明確指定 > dialogue-state.json 儲存值 > sdd_context 推導（S2→spec, S5→code, S6→test）> fail-fast。

---

## 硬性規則

1. 最多 **20 輪**。
2. 收斂條件：`spec` 依 Output Schema；`code` P0=P1=0（P2 容忍）；`test` P0=P1=P2=0。
3. 禁止跳過 Codex，每輪必經 Codex CLI。
4. 收到 Codex findings 後必須自行 grep/read 獨立驗證。
5. defend 必須附 counter-evidence（file:line 或 spec 段落）。
6. 修正保守：只修 Codex 指出的問題。
7. Bounded Read：不讀全部歷史，遵循 dialogue-index.json 策略。
8. 每個 finding 需有 evidence，ID 格式：SR-/CR-/TR-。
9. test scope 修正後必須重跑測試。

---

## 流程

### 0. 初始化

解析參數：`/review-dialogue <target> [scope] [resume]`
建立 `$DIALOGUE_DIR = $SPEC_FOLDER/review/dialogue`。
檢查既有 state：in_progress → 詢問續輪；approved → 詢問重新開始；不存在 → 新 dialogue。

### 1. Claude Submit（Turn 1）

依 scope 組裝 Context（review-standards + output-schema + 對應檔案），寫入 turn-001-claude-submit.md。
初始化 dialogue-state.json + dialogue-index.json。
透過 codex-liaison Agent 呼叫 Codex。

### 2. 讀取 Codex Review Turn

解析 findings（ID, severity, evidence, status）。顯示狀態面板（P0/P1/P2 + new/resolved/defended）。

### 3. 收斂檢查

APPROVED → 步驟 6。CONTINUE 且未超 max_turns → 步驟 4。超過 → 步驟 7。同一 finding 連續 2+ 輪 defended→rejected → Deadlock 步驟 8。

### 4. Claude 驗證 + 回應

對每個 finding 獨立驗證（Grep/Read）：
- 問題確實存在 → `accept_and_fix`（spec 修 spec、code 修 code、test 修 code+重跑）
- 問題不存在 → `defend` 附 counter-evidence

寫入 turn-{N}-claude-response.md。

### 5. 更新 State + Index → 呼叫 Codex

更新 dialogue-state/index，透過 codex-liaison 呼叫下一輪。回到步驟 2。

### 6. 收斂完成
更新 state：`approved`。code scope 最終全量建置驗證；test scope 全量測試確認。

### 7. 未收斂強制停止
state：`max_turns_reached`。列出未解決 findings。

### 8. Deadlock
state：`deadlocked`。列出死鎖 findings，由用戶裁定。

---

## Bounded Read 策略

每輪讀取：最新 Codex turn（必讀）→ dialogue-index unresolved（必讀）→ 最近 4 輪（補充）→ 更早 turns 僅在需 evidence 時回讀。
