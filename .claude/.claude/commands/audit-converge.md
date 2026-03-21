---
description: "Audit 收斂 — 循環審計修復至 P0=P1=P2=0"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Task, mcp__sequential-thinking__sequentialthinking
argument-hint: "<spec 目錄路徑 | latest>"
---

# /audit-converge — 自動審計修復收斂迴圈

> 自動循環 spec-audit（6-Agent）→ fix → 直到 P0=P1=P2=0 或 10 輪上限。
> `/spec-converge` 修 Spec 文字；`/audit-converge` 修 Code 實作。

## 環境資訊
- 當前分支: !`git branch --show-current`
- Codex: !`codex --version 2>/dev/null || echo "NOT FOUND"`

## 輸入
- Spec 目錄：$ARGUMENTS（`latest` → 找最新 `dev/specs/*/sdd_context.json`）

---

## 硬性規則

1. 最多 **10 輪**。
2. 收斂條件：P0=0 且 P1=0 且 P2=0。
3. 停滯偵測：連續 3 輪 total 無變化 → 提前中斷（STALE）。
4. 審計用 spec-audit 引擎（`.claude/commands/spec-audit.md`）。
5. 修復 Codex 優先，Fallback Claude Task(opus)。
6. 修復保守：只修審計指出的問題。
7. 不刪除檔案。
8. spec_fix 跳過（需人工決策），只修 `code_fix` + `test_fix`。

---

## Phase 0：初始化

```bash
SESSION_DIR="$SPEC_FOLDER/audit-converge/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$SESSION_DIR"
```

驗證 s0_brief_spec.md + s1_dev_spec.md + sdd_context.json 存在。
初始化 convergence-state.json（max_rounds:10, stale_threshold:3）。

## Phase 1：迴圈（Round 1~10）

### 1.1 審計
執行 spec-audit 引擎。Round 1 完整 Phase 1~4；Round 2+ 跳 Phase 1（清單不變）。每輪執行 Phase 5 持久化 + 備份到 session dir。

### 1.2 收斂檢查
P0=P1=P2=0 → CONVERGED(Phase 2)。N=10 → MAX_ROUNDS(Phase 3)。連續 3 輪 total 不變 → STALE(Phase 3)。

### 1.3 修復
解析 findings → code_fix/test_fix/spec_fix(跳過)。按 P0→P1→P2 排序，每批最多 5 個。
Codex 修復（sandbox:workspace-write, timeout:180s），失敗 → Claude Task(opus)。
記錄結果 + git diff 到 session dir。回到 1.1。

## Phase 2：收斂完成
顯示歷程面板，convergence-state: `converged`。

## Phase 3：未收斂停止
顯示歷程 + 剩餘 P0/P1 findings + 建議，convergence-state: `max_rounds|stale`。

---

## Session 目錄結構
```
{spec_folder}/audit-converge/{SESSION_TS}/
├── convergence-state.json
├── round-{N}-audit.md / round-{N}-fix.md / round-{N}-diff.txt
└── final-changes.diff
```
