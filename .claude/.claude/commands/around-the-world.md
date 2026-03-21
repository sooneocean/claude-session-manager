---
description: "Around the World — 批次 feature 連續 autopilot"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Task, mcp__sequential-thinking__sequentialthinking
argument-hint: "<feature1> | <feature2> | ... OR resume OR status OR add <feature>"
---

# /atw — Around the World

> Autopilot = 一趟航班。ATW = 環球航行，批次 feature 自動連跑。
> 每個 feature 之間強制 compact，保證乾淨 context。

## 環境資訊
- 當前分支: !`git branch --show-current 2>/dev/null || echo "(未初始化)"`
- ATW Session: !`cat dev/atw-session.json 2>/dev/null | jq -r '"status=" + .status + " completed=" + (.stats.completed|tostring) + "/" + (.stats.total|tostring)' 2>/dev/null || echo "無"`

## 輸入
指令：$ARGUMENTS

---

## 參數解析

| 輸入 | 模式 | 行為 |
|------|------|------|
| `"Feature A" \| "Feature B" \| ...` | 啟動 | 建立 ATW session，queue 所有 feature |
| `resume` | 恢復 | 讀取 atw-session.json，從中斷點繼續 |
| `status` | 狀態 | 顯示 ATW 進度 dashboard |
| `add <description>` | 追加 | 往現有 queue 追加 feature |
| `pause` | 暫停 | 暫停 ATW，保留 queue |
| `cancel` | 取消 | 取消整個 ATW session |

---

## 模式 A：啟動新 ATW Session

### 1. 解析 feature 清單

從 `$ARGUMENTS` 解析，支援：
- Pipe 分隔：`"Feature A" | "Feature B" | "Feature C"`
- 換行分隔（多行輸入）
- 指向 master spec：`dev/specs/xxx/s0_brief_spec.md`（讀取 FA 拆解表自動建 queue）

### 2. 建立 session

```bash
mkdir -p dev
```

寫入 `dev/atw-session.json`：

```json
{
  "session_id": "ATW-{YYYYMMDD}-{HHmmss}",
  "created_at": "ISO8601",
  "status": "in_progress",
  "s0_gate": "per_feature",
  "current_feature_id": 1,
  "features": [
    {
      "id": 1,
      "description": "Feature A description",
      "status": "queued",
      "spec_folder": null,
      "commit_hash": null,
      "branch": null,
      "started_at": null,
      "completed_at": null,
      "error": null
    }
  ],
  "stats": {
    "total": 0,
    "completed": 0,
    "in_progress": 0,
    "queued": 0,
    "failed": 0,
    "skipped": 0,
    "total_commits": 0,
    "total_files_changed": 0
  }
}
```

### 3. 顯示啟動面板

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌍 Around the World — 啟動
   Session: {session_id}
   Features: {total} 個排隊
   S0 Gate: per_feature（每個 feature 確認需求）

   Queue:
   1. ⏳ Feature A
   2. ⏳ Feature B
   3. ⏳ Feature C

   → 開始 Feature 1...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 4. 開始第一個 feature

```
更新 atw-session.json:
  features[0].status = "in_progress"
  features[0].started_at = now()
  current_feature_id = 1
  stats.in_progress = 1, stats.queued -= 1

Skill(skill: "s0-understand", args: "{feature description}")
```

遵循標準 Autopilot 流程（S0→S7）。S0 Gate 仍然 🔴 必停。

---

## Feature 完成後的 ATW 鏈

**S7 完成時（由 Orchestrator 檢查）：**

1. 讀取 `dev/atw-session.json`
2. 若 ATW session 活躍：
   a. 更新當前 feature：`status: "completed"`, `commit_hash`, `completed_at`
   b. 更新 stats
   c. 檢查是否有 queued features 剩餘

3. **若有下一個 feature：**
   ```
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   🌍 ATW Feature {N}/{total} 完成 ✅
      Commit: {hash}
      進度: {completed}/{total} features

      → 強制 compact 清理 context...
      → 下一個: Feature {N+1}
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   ```

   更新 `current_feature_id = N+1`
   **告知用戶執行 `/compact`**（ATW 強烈建議，但不能程式化執行 compact）
   compact 後 sop-compact-reminder.sh 會偵測 ATW session 並注入下一個 feature

4. **若全部完成：**
   ```
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   🌍 Around the World 完成！🎉
      Session: {session_id}
      Features: {completed}/{total}
      Total commits: {n}
      Total files: {n}

      完成清單:
      1. ✅ Feature A → {commit_hash}
      2. ✅ Feature B → {commit_hash}
      3. ❌ Feature C → 失敗（{error}）
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   ```
   更新 session `status: "completed"`

---

## Feature 失敗處理

當某 feature 的 SOP 觸發安全中斷（S5 P0、迴圈超限等）：

1. 顯示中斷原因
2. 問用戶：
   - 「修復」→ 修復當前 feature 的問題
   - 「跳過」→ 標記 `status: "skipped"`，繼續下一個
   - 「暫停 ATW」→ 暫停整個 session
   - 「取消」→ 取消剩餘 queue

---

## 模式 B：恢復（resume）

1. 讀取 `dev/atw-session.json`
2. 找 `current_feature_id` 對應的 feature
3. 若該 feature 有 `spec_folder`：
   - 讀取 sdd_context.json
   - 從 `current_stage` 繼續 autopilot
4. 若該 feature 還是 queued：
   - 啟動 S0

---

## 模式 C：狀態（status）

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌍 Around the World — 進度
   Session: {session_id}
   Status: {in_progress | paused | completed}
   進度: {completed}/{total} ({percentage}%)

   1. ✅ Feature A      → abc1234 (12 files)
   2. 🔄 Feature B      → S4 實作中
   3. ⏳ Feature C      → 排隊
   4. ❌ Feature D      → S5 P0 失敗
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 模式 D：追加（add）

```bash
/atw add 新增一個會員等級功能
```

1. 讀取 atw-session.json
2. Append 新 feature 到 queue 尾端
3. 更新 stats.total + stats.queued

---

## sop-compact-reminder 整合（Node-Aware）

compact 後 `sop-compact-reminder.sh` 的恢復路徑：

1. **Node recovery（優先）**：讀取已完成 feature 的 S7 node → 其 Next Input 包含 Feature Summary + ATW Next → 直接注入完整交接 context
2. **ATW fallback**：若 node 不存在，讀 `atw-session.json` → 找 current_feature_id → 注入 feature description
3. **Guard**：node recovery 成功時跳過 ATW 獨立注入（防止雙重注入）

**feature 邊界的完整資訊流**：
```
S7 完成 → 寫 S7 node (含 Feature Summary + ATW Next) → 更新 atw-session.json
→ 用戶 /compact → hook 讀 S7 node → 注入 Feature Summary + 下一個 feature S0 指令
→ Claude 啟動下一個 feature 的 S0，帶著上一個 feature 的 context
```

---

## 安全規則

- 每個 feature 的 S0 Gate 仍然 🔴 必停（預設）
- S5 P0 / 迴圈超限 → 中斷但不殺 queue
- 用戶隨時可「暫停 ATW」
- 不自動 push（同 autopilot）
- atw-session.json 是唯一 session 狀態，不在 sdd_context 內

---

## 與其他模式的關係

| 模式 | 範圍 | Context 管理 | 適用 |
|------|------|-------------|------|
| Manual | 單 stage | 無 | 學習/除錯 |
| Semi-Auto | 單 feature | 無 | 需控制的任務 |
| Autopilot | 單 feature | 建議 compact | 大部分任務 |
| **Around the World** | **批次 feature** | **強制 compact** | **長時間連續開發** |
