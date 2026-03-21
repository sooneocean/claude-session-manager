---
description: "S0 需求討論 — 互動式理解需求並產出共識"
allowed-tools: Read, Grep, Glob, Task, mcp__sequential-thinking__sequentialthinking
argument-hint: "<需求描述 或 需求模板檔案路徑>"
---

# S0 需求討論（互動式）

## 環境資訊
- 當前分支: !`git branch --show-current 2>/dev/null || echo "(未初始化)"`
- 專案狀態: !`git status --porcelain 2>/dev/null | head -10`

## 前置檢查：Git Repository

若上方顯示 `(未初始化)`，先執行 `git init -b main && git add . && git commit -m "Initial commit"`，再建 GitHub repo（`gh repo create`）。

## 輸入
需求描述：$ARGUMENTS

---

## 輸入模式判斷

### 模式 A：結構化輸入
條件：`$ARGUMENTS` 含模板標記或指向 .md 檔。
流程：讀取 → 直接確認+補充 → 只針對缺漏提 2-3 個問題 → 產出共識。

### 模式 B：自然語言
流程：初步理解 → 主動提問 → 互動至共識 → 產出。
模糊時提供模板：`dev/specs/_templates/s0_requirement_input_template.md`

---

## Agent 調度：`requirement-analyst` (sonnet)

Prompt 要點：判斷 work_type → 依 work_type 調整提問策略 → 用 sequential-thinking 分析 → 依六維度框架（`.claude/references/exception-discovery-framework.md`）探測例外 → 產出需求共識。

---

## 任務流程

1. **判斷輸入模式**：模板 or 自然語言
2. **判斷 work_type**：模板勾選 > 信號詞（新增→new_feature、壞了→bugfix、重構→refactor、調查→investigation）> 主動詢問
3. **初步理解**（依 work_type 調整）：
   - new_feature：5W1H
   - refactor：哪裡不滿意？理想狀態？
   - bugfix：重現步驟？預期 vs 實際？
   - investigation：觀察到什麼？初步猜測？
4. **FA Decomposition**：識別獨立業務領域，評估拆解策略：
   - 1~2 FA / 低獨立性 → `single_sop`
   - 3~4 FA / 中~高 → `single_sop_fa_labeled`
   - 4+ FA / 高 → `multi_sop`（討論拆分）
5. **互動確認**：需求正確？FA 合理？成功標準明確？範圍？例外？約束？
   - 六維度例外探測（依 `.claude/references/exception-discovery-framework.md` §1，每個維度至少 1 問）
6. **Spec Mode**：Quick（bugfix/≤3檔/無DB API/≤2任務）vs Full Spec（new_feature/3+檔/DB API/3+任務）
7. **方案比較**（new_feature/refactor）：2-3 個方案比較表。bugfix/investigation 可跳過。
8. **產出需求共識**：
   - Full Spec → `{spec_folder}/s0_brief_spec.md`（模板見 `dev/specs/_templates/s0_brief_spec_template.md`），含 §4.0 FA 拆解 + 每 FA 流程圖 + 例外流程圖
   - Quick → 對話中，不產出文件（仍需走精簡六維度探測）
   - Multi-SOP → 本文件為 Master Spec，子 SOP 記錄於 `child_sops`

---

## SDD Context 持久化

> 見 `.claude/references/sdd-context-persistence.md`（S0 區段）

S0 **建立** sdd_context.json：version, feature, spec_mode, work_type, s0.output。
路徑：`{spec_folder}/sdd_context.json`（Quick 也建立）。

---

## Checkpoint Node Write（MUST）

S0 Gate 通過後、前端偵測前，**必須**寫入 checkpoint node：

1. `mkdir -p {spec_folder}/nodes/`
2. 生成序號（掃描 nodes/ 取最大 +1，起始 000）
3. 寫入 `{spec_folder}/nodes/node-{NNN}-s0-consensus.md`：
   - Conclusion: "Requirement consensus reached: {1-sentence}. work_type={type}, spec_mode={mode}."
   - Artifacts: brief_spec path (Full Spec) or "對話中" (Quick)
   - Next Input: work_type, top 5 scope_in, top 3 constraints, top 3 pain_points. Full spec: "see s0_brief_spec.md"
   - Gate: Result=passed, Next Stage=S1, Next Action="Run S0→S1 frontend detection, then start S1 technical analysis."
4. `echo "node-{NNN}-s0-consensus.md" > {spec_folder}/nodes/CURRENT`
5. 繼續 SDD Context 持久化（既有邏輯）

> 格式見 `dev/specs/_templates/node_template.md`

---

## S0 Gate

🔴 **必停！等待用戶確認。**

✅「繼續」→ 寫 checkpoint node → 執行前端偵測 → S1。✏️ 修改意見 → 調整 brief_spec。

---

## S0→S1 前端偵測（MUST）

### Step 1：關鍵字掃描
讀取 brief_spec，掃描前端關鍵字（畫面/UI/form/button/nav/modal/React/Flutter 等）。命中 ≥2 → Step 2。<2 → 直接 S1。

### Step 2：設計檔案偵測
檢查 `{spec_folder}/frontend/` 和 `.superpowers/brainstorm/` 是否有 flowchart/wireframe/mockup.html。找到 → 複製到 spec 目錄。

### Step 3：自動觸發前端設計管線
flowchart skill（已存在則跳過）→ wireframe skill（已存在則跳過）→ 進入 S1。
