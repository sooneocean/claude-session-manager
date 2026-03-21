# SOP 規則與階段定義

> Gate 策略、Autopilot 狀態機見 `conductor-protocol.md`
> SDD Context schema 見 `sdd-context-schema.md`

## S0~S7 階段定義

| Stage | Agent | 產出 | Gate |
|-------|-------|------|------|
| S0 需求討論 | requirement-analyst | brief_spec + sdd_context | 🔴必停 |
| S1 技術分析 | codebase-explorer + architect | dev_spec | 🟢自動 |
| S2 Spec Review | Codex/Opus + architect | review_report（Quick 跳過） | 🟢自動 |
| S3 執行計畫 | architect | implementation_plan | 📋摘要 |
| S4 實作 (TDD) | 依任務類型 | 變更清單 + tdd_evidence | 🟢自動 |
| S5 Code Review | reviewer + 審查引擎 | review_report | pass→S6/P1→S4/P0→S1 |
| S6 驗收測試 | test-engineer + debugger | test_checklist | pass→S7/fail→修復(≤3) |
| S7 提交 | git-operator | commit + lessons_learned | 🟢auto-commit |

### S5 回饋迴路
- P0 設計問題 → 回 S1
- P1 實作問題 → 回 S4（≤3 次，超過中斷）
- P2 建議 → 記錄後繼續

### S6 驗收閉環
- TDD 審計失敗 → P1 回 S4
- E2E/整合缺陷 → debugger 診斷 + 修復（走 TDD）→ 重測（≤3 次）

---

## Spec Mode 判斷

### Quick（對話模式）
- bug fix / 文字調整 / ≤3 檔 / 無 DB API 變更 / ≤2 任務
- 不產出 spec 文件，S2 跳過

### Full Spec（文件模式）
- 新功能 / 3+ 檔 / DB schema 或 API 變更 / 架構重構 / 3+ 任務
- 產出 .md 文件，S2 完整審查

用戶覆寫：「寫 spec」→ Full；「不用 spec」→ Quick。灰色地帶主動問。

---

## 文件目錄結構

```
dev/specs/{YYYY-MM-DD}_{N}_{feature-name}/
├── s0_brief_spec.md
├── s1_dev_spec.md
├── s2_review_report.md
├── s3_implementation_plan.md
├── s5_code_review_report.md
├── s6_test_checklist.md（視需要）
├── sdd_context.json
└── frontend/（前端偵測通過時）
```

命名：日期+序號，kebab-case。模板：`dev/specs/_templates/`

---

## 知識管理

### Pitfalls Registry（`dev/knowledge/pitfalls.md`）

格式：`### [tag] 標題` + 錯誤/正確/來源。
Tags：`db`, `flutter`, `dotnet`, `arch`, `security`, `test`, `design`, `api`。

自動追加：S5 P1 問題（reviewer）、S6 缺陷（test-engineer）、S7 new_pitfalls（git-operator）。
S1 消費：codebase-explorer 掃描 pitfalls + 歷史 lessons_learned 注入風險評估。

### Lessons Learned（S7 自動捕獲）
git-operator 生成 what_went_well / what_went_wrong / new_pitfalls → 寫 sdd_context → append pitfalls.md。

---

## S4 實作調度

> Manifest-Aware：讀 `.claude/manifest.json` 確認可用 agents。

| 任務類型 | Agent | 條件 |
|---------|-------|------|
| 前端 UI | frontend-developer | 始終可用 |
| 錯誤診斷 | debugger | 始終可用 |
| DB schema | 對應 stack agent | 需 database stack |
| 後端邏輯 | 對應 stack agent | 需 stack |
| 無匹配 | Orchestrator 直接實作 | — |
