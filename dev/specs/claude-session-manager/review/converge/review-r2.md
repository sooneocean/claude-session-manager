# Spec Converge Review — Round 2

> engine: fallback (codex 401 Unauthorized)
> scope: spec
> target: dev/specs/claude-session-manager/review/converge/spec-current.md

---

## Round 1 修正驗證摘要

| Finding ID | 修正項目 | 狀態 |
|-----------|---------|------|
| SR-P1-001 | WAIT 判定改由 SessionManager 負責，定義 5 秒超時 | 已修正 |
| SR-P1-002 | Wave 0 NO-GO 時 Task #6 備案 DoD | 已修正 |
| SR-P1-003 | 介面契約補充 QueueFullError | 部分修正（見下） |
| SR-P1-004 | 明確成本資料流向（SessionState→CostAggregator） | 已修正 |
| SR-P1-005 | Task #7 可用 stub OutputParser 並行開發 | 已修正 |
| SR-P2-001 | ANSI DoD 列舉 3 種具體 pattern | 已修正 |
| SR-P2-002 | 補充 CostSummary dataclass 定義 | 已修正 |
| SR-P2-003 | Task #0 補充 pytest dev dependency | 已修正 |

---

## Findings

### [SR-P1-001] P1 - QueueFullError TUI 處理層仍未定義

- id: `SR-P1-001`
- severity: `P1`
- category: `completeness`
- file: `spec section 5.2 Task #12 / 4.1`
- line: N/A
- rule: 所有 exception path 必須定義系統行為和用戶回饋
- evidence: R1 修正摘要對 SR-P1-003 要求三件事：(1) 介面契約補充 QueueFullError（已完成，見 4.1 CommandDispatcher 的 Raises 清單）；(2) Task #12 描述中加入 QueueFullError 的 TUI 處理邏輯；(3) AC 或 E1 補充 queue 滿時預期用戶體驗。Task #12 描述列出 10 項職責（行 601-619），無任何一項提及 QueueFullError 的捕捉與顯示邏輯。驗收標準 AC-1 至 AC-10 和異常流程表 E1-E6 均無覆蓋 queue 滿情境。
- impact: 實作 Task #12 時，QueueFullError 從 CommandDispatcher 向上拋出後，app.py 沒有 spec 依據決定如何處理，可能導致未捕捉例外使整個 TUI 崩潰，或靜默吞掉錯誤讓使用者不知道指令未送出。
- fix: 在 Task #12 描述職責清單加入第 11 項：「捕捉 QueueFullError，顯示『指令佇列已滿，請稍後再試』提示」。同時在 E1 異常流程行說明補充：queue 滿（maxsize=50 已達上限）時的用戶可見行為。

---

### [SR-P1-002] P1 - Task #7 DoD 缺少 WAIT 狀態判定的可測試條目

- id: `SR-P1-002`
- severity: `P1`
- category: `completeness`
- file: `spec section 5.2 Task #7`
- line: N/A
- rule: DoD 必須覆蓋任務描述中定義的所有核心行為
- evidence: Task #7 描述（行 519-524）現已明確：「stdout reader task 在最後一次收到 stdout 輸出後，若 5 秒無新輸出，則將 session 標記為 WAIT」。但 Task #7 DoD（行 525-531）的六個條目為：spawn/stop/restart、crash detection、E4/E5、reader task 啟動清理、Windows terminate、自動化測試覆蓋（僅列 spawn 成功/DirectoryNotFoundError/DuplicateSessionError/terminate→kill/crash→DEAD）。DoD 自動化測試清單和 DoD 條目均無「無輸出 5 秒後標記 WAIT」的驗收項目。
- impact: WAIT 判定是 SR-P1-001 修正後新增的核心職責，若 DoD 不要求驗證此行為，實作者可以跳過計時邏輯、永遠不設 WAIT，仍然通過所有 DoD 條目，導致 AC-5（發送指令）在實際使用時因 session 不進入 WAIT 狀態而操作失靈。
- fix: 在 Task #7 DoD 補充：「WAIT 狀態判定：stdout reader task 5 秒無新輸出後正確將 session 標記為 WAIT」；並在自動化測試清單加入：「asyncio 時間 mock 驗證 5 秒超時後 status 變為 WAIT」。

---

## Summary

- totals: `P0=0, P1=2, P2=0`
- decision: `REJECTED`
