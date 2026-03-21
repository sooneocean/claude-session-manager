---
description: "Spec 深度審計 — 6 Agent 並行比對 Spec 與 codebase"
allowed-tools: Read, Grep, Glob, Bash, Task, mcp__sequential-thinking__sequentialthinking
argument-hint: "<spec 目錄路徑>"
---

# Spec 深度審計（6-Agent 並行引擎）

## 環境資訊
- 當前分支: !`git branch --show-current`

## 輸入
- Spec 目錄路徑：$ARGUMENTS（若無引數，提示提供 `dev/specs/{folder}/`）

## 雙入口模式

| 模式 | 觸發方式 | 輸出 |
|------|---------|------|
| **獨立模式** | `/spec-audit dev/specs/xxx/` | Markdown + 寫入 `{spec_folder}/audit/` |
| **S5 整合模式** | 由 s5-review 內部調用 | JSON 回傳供 S5 寫入 sdd_context |

判斷：上下文含 `s5-review` 或 `spec_verification` → 整合模式；否則獨立模式。

---

## Phase 1：解析 Spec → 6 維度審計清單

讀取 `{spec_folder}/` 下 s0_brief_spec.md、s1_dev_spec.md、sdd_context.json、s1_api_spec.md（若存在）。

用 sequential-thinking 拆解為 6 維度：

| 維度 | 來源 |
|------|------|
| D1 Frontend | S0 §6 scope_in 前端 + S1 tasks 前端 |
| D2 Backend | S0 §6 scope_in 後端 + S1 tasks 後端 |
| D3 Database | S0 §6 scope_in DB + S1 tasks DB |
| D4 User Flow | S0 §4 mermaid 流程圖的每條路徑 |
| D5 Business Logic | S0 §4 異常表 + §7 約束 + §9 Data Flow |
| D6 Test Coverage | S0 §4 異常表 + S1 acceptance_criteria |

每個審計項包含：維度、ID（序號）、描述（可 Grep 粒度）、來源（Spec 段落引用）、錨定的成功標準。

---

## Phase 2：6-Agent 並行調度

同一 message 發出全部 6 個 Agent（Explore, sonnet）。每個 Agent 收到其維度審計清單。

### 共用輸出格式

所有 Agent 產出 JSON：
```json
{
  "dimension": "d{N}_{name}",
  "findings": [
    { "id": "SA-D{N}-{NNN}", "item": "描述", "status": "passed|partial|failed", "evidence": "file:line", "severity": "P0|P1|P2", "note": "" }
  ],
  "summary": { "total": 0, "passed": 0, "partial": 0, "failed": 0 }
}
```

### 各 Agent 驗證重點

| Agent | 維度 | 核心驗證 |
|-------|------|---------|
| A Frontend | D1 | scope_in 前端項→Grep 前端目錄、狀態管理、設計系統、API Client endpoint |
| B Backend | D2 | scope_in 後端項→Grep 後端目錄、Route/Endpoint、Service 業務邏輯、TX 邊界 |
| C Database | D3 | 表結構 vs spec、ORM Entity、Migration、Index、FK |
| D User Flow | D4 | **核心差異化**：逐步追蹤 UI→Event→Handler→API→Service→Repo→DB→Response→UI，每步標記 ✅⚠️❌ |
| E Business Logic | D5 | 異常表→error handling、約束→validation、DTO 跨層一致性 |
| F Test Coverage | D6 | 異常表→test case 映射、AC→test、約束→邊界 test；金錢/安全無 test→P1 |

D4 User Flow 額外輸出 `flows[]` 陣列（每條 flow 的 steps）。

### 降級策略
Agent 120s 超時 → retry 1x (opus) → 標記 `[DEGRADED]` → 全失敗回退淺層 Grep。

---

## Phase 3：交叉驗證矩陣（Orchestrator 執行）

| 交叉 | 比對內容 | Finding 前綴 |
|------|---------|-------------|
| Frontend × Backend | endpoint/method/DTO 一致性 | SA-CROSS-API- |
| Backend × Database | Entity 屬性 vs DB schema | SA-CROSS-DB- |
| User Flow × Business Logic | 邊界情境是否落在 Flow 路徑上 | SA-CROSS-FLOW- |
| Business Logic × Test | 邊界有 code 但無 test → 未測試邊界 | SA-CROSS-TEST- |
| 成功標準錨定 | S0 §5 每條標準 × 各維度子項 → 通過/部分/未達 | — |

---

## Phase 4：報告

獨立模式輸出 Markdown：審計摘要 → 6 維度覆蓋矩陣 → 交叉驗證 → 成功標準錨定 → User Flow 追蹤明細 → Gap List (P0→P1→P2) → 證據索引。

S5 整合模式回傳 JSON（含 dimensions、cross_validation、engine_status、findings_summary、issues[]）。

---

## Phase 5：Persist & Track

1. `mkdir -p {spec_folder}/audit/history`
2. 寫入 `{spec_folder}/audit/spec_audit_report.md` + `audit_summary.json`（覆蓋）
3. 歷史快照到 `{spec_folder}/audit/history/{timestamp}/`
4. Append `sdd_context.json` 的 `audit_history[]`；S5 整合模式額外寫 `stages.s5.output.spec_audit`
5. 更新 `last_updated`

## 注意事項
- 純讀取：不修改 codebase
- 每個 finding 必須附 `file:line` 證據
- 不做 code quality 審查（那是 R1 職責）
