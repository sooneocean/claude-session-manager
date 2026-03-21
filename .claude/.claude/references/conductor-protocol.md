# Conductor Protocol — SDD 智慧調度協議

> Orchestrator 在 Autopilot 模式下的行為規範（含原 orchestrator-behavior 內容）。

## 1. 意圖路由器

用戶輸入分類為 4 類：

| 分類 | 判斷依據 | 動作 |
|------|---------|------|
| SOP 任務 | 建設性動詞（做/加/改/修/新增/重構/修復） | Autopilot S0→S7 |
| 獨立 Skill | Skill 關鍵字（見 system prompt skill descriptions） | 直接調用 |
| 直接操作 | 查詢/確認/瀏覽 | 直接執行 |
| SOP 控制 | 進度/繼續/暫停/切換 | 恢復或控制 SOP |

work_type 推斷：新增→new_feature、壞了/bug→bugfix、重構/優化→refactor、調查/為什麼→investigation。
衝突時主動詢問用戶。

---

## 2. 執行模式

| 模式 | 說明 | 切換語句 |
|------|------|---------|
| **Autopilot**（預設） | S0 確認後全自動 | 「autopilot」 |
| Semi-Auto | S0+S3 必停 | 「不要 autopilot」 |
| Manual | 全停 | 「全手動」 |

`sdd_context.execution_mode` 記錄當前模式。

---

## 3. Autopilot 狀態機

```
IDLE → S0 🔴確認 → [前端偵測] → S1 🟢 → S2(Quick跳過) 🟢 → S3 📋摘要 → S4 🟢 → S5
S5 pass → S6。S5 P1 → S4(≤3次)。S5 P0 → ⚠️中斷
S6 pass → audit-converge。S6 fail → 修復(≤3)
AC converged → S7 auto-commit → ✅DONE。AC not → ⚠️中斷
```

### Gate 策略

| 轉換 | Autopilot | Semi-Auto | Manual |
|------|-----------|-----------|--------|
| S0→S1 | 🔴必停 | 🔴必停 | 🔴必停 |
| S1→S2→S3 | 🟢自動 | 🟢自動 | 🔴必停 |
| S3→S4 | 📋摘要通知 | 🔴必停 | 🔴必停 |
| S4→S5→S6 | 🟢自動 | 🟢/🟡 | 🔴必停 |
| AC→S7 | 🟢自動 | 🟡確認 | 🔴必停 |

### S0→S1 前端偵測（必執行）

S0 確認後掃描 brief_spec 前端關鍵字（UI/form/button/nav/modal/React/Flutter 等）。
命中 ≥2 → 自動 flowchart skill → wireframe skill → S1。
命中 <2 → 直接 S1。

### Auto-Chain 協議

每個 Skill 完成後：讀 sdd_context → 判斷 execution_mode → 依狀態機推進下一階段。
特殊：S5 P1 檢查 repair_loop_count < 3；S6 pass 自動 audit-converge；AC converged 繼續 S7。

---

## 4. 安全中斷

| 條件 | 行為 |
|------|------|
| S5 P0 | 🔴阻斷，需人工裁決 |
| S4↔S5 迴圈 3 次 | 🔴阻斷 |
| S6 修復 3 次 | 🔴阻斷 |
| AC 未收斂 | 🔴阻斷 |
| Agent 崩潰 | 🟡降級處理 |
| 用戶說「停」 | 🔴立即暫停 |
| SDD Context 損壞 | 🔴阻斷 |

暫停：`sdd_context.autopilot_paused: true`。恢復：用戶說「繼續」。

---

## 5. Context 壓縮策略（1M context 校準）

| 階段結束 | 建議 |
|---------|------|
| S1 完成 | 🟡 建議 compact（explorer 大量 Read/Grep） |
| S4 完成 | 🟡 建議 compact（tool call 密集） |
| S5 P1→S4 迴圈前 | 🟡 建議（清除審查對話） |

compact 後 `sop-compact-reminder.sh` 自動恢復 SDD Context。

---

## 6. Cost Awareness

cost-tracker.sh（Stop hook）追蹤 session 成本。閾值：$2(notice) / $5(warning) / $10(critical)。
S7 完成時彙整 `sdd_context.pipeline_cost`。

---

## 7. Failed Approaches Tracking

| 時機 | 寫入位置 |
|------|---------|
| S1 棄選方案 | s1.output.failed_approaches |
| S4 實作失敗 | s4.output.failed_approaches |
| S5 redesign | s5.output.failed_approaches + 頂層 |
| S4↔S5 安全閥 | 頂層 |

格式：`{"approach":"描述", "reason":"原因", "timestamp":"ISO8601"}`
compact 恢復時顯示已知失敗路徑。

---

## 8. Quality Gate

quality-gate.sh（PostToolUse on Edit|Write）：偵測 linter config → auto-format。
偵測：biome.json→Biome、.prettierrc→Prettier、eslint→ESLint、ruff→Ruff、go.mod→gofmt。
與 S5 分工：hook 管格式，S5 管邏輯。
