# Spec Converge Review — Round 3

> engine: fallback (codex 401 Unauthorized)
> scope: spec
> target: dev/specs/claude-session-manager/review/converge/spec-current.md

---

## 前輪修正驗證摘要

| Finding ID | 修正項目 | 驗證結果 |
|-----------|---------|---------|
| R1-SR-P1-001 | WAIT 判定改由 SessionManager 負責，定義 5 秒超時 | 已確認（spec-current.md 行 504） |
| R1-SR-P1-002 | Wave 0 NO-GO 時 Task #6 備案 DoD | 已確認（行 509） |
| R1-SR-P1-003 | 介面契約補充 QueueFullError | 已確認（行 303） |
| R1-SR-P1-004 | 明確成本資料流向（SessionState→CostAggregator） | 已確認（行 337-339） |
| R1-SR-P1-005 | Task #7 可用 stub OutputParser 並行開發 | 已確認（行 518） |
| R1-SR-P2-001 | ANSI DoD 列舉 3 種具體 pattern | 已確認（行 464） |
| R1-SR-P2-002 | 補充 CostSummary dataclass 定義 | 已確認（行 361-365） |
| R1-SR-P2-003 | Task #0 補充 pytest dev dependency | 已確認（行 411） |
| R2-SR-P1-001 | Task #12 DoD 加入 QueueFullError 捕捉與顯示 | 已確認（行 621） |
| R2-SR-P1-002 | Task #7 DoD 加入 WAIT 5 秒超時測試 | 已確認（行 532） |

---

## Findings

### [SR-P1-001] P1 - Task #13 DoD 聲稱「7 個成功標準」但驗收標準實際有 10 條

- id: `SR-P1-001`
- severity: `P1`
- category: `completeness`
- file: `spec section 5.2 Task #13 / 7.1`
- line: `633`
- rule: DoD 覆蓋聲明必須與實際驗收標準數量一致
- evidence: Task #13 DoD 第二條（行 633）：「手動測試清單覆蓋 7 個成功標準」。Section 7.1 定義 AC-1 到 AC-10 共 10 條驗收標準，含 P0 級別的 AC-8（Crash 偵測）和 P1 級別的 AC-10（Resume session）。「7」與「10」數量不符，且無說明哪 3 條被排除及原因。
- impact: Task #13 實作者若按 DoD 字面執行，只需覆蓋 7 條，AC-8（Crash 偵測 P0）、AC-9（篩選排序）、AC-10（Resume session）有被合法跳過的空間，導致核心功能驗收漏洞。
- fix: 將行 633 改為「手動測試清單覆蓋 10 個驗收標準（AC-1 至 AC-10）」；若有意排除某些 AC，需明文列出並說明原因。

---

### [SR-P1-002] P1 - CommandDispatcher 呼叫 notify_crash(session_id) 的跨元件介面未定義

- id: `SR-P1-002`
- severity: `P1`
- category: `architecture`
- file: `spec section 4.1 / 4.0 Data Flow / Task #8`
- line: `241`（Data Flow）、`300-303`（4.1 介面契約）
- rule: 跨元件呼叫的介面契約必須完整定義，包含依賴注入方式
- evidence: Data Flow 圖（行 241）明確顯示 `CP->>SM: notify_crash(session_id)`，即 CommandDispatcher 在捕捉 BrokenPipeError 後需回報 SessionManager。但 4.1 CommandDispatcher 介面契約只定義 `enqueue` 方法，沒有任何說明：(1) CommandDispatcher 如何持有 SessionManager 的參考（建構子注入？全域？）；(2) `notify_crash` 是 SessionManager 的公開方法還是 callback；(3) Task #8 描述（行 541）只說「觸發 crash 流程」，無法推導具體實作路徑。
- impact: CommandDispatcher 與 SessionManager 的耦合點完全由實作者自行決定，可能導致循環依賴、介面不一致，或實作者直接忽略 BrokenPipeError → crash 回報的連結，造成 session 狀態機停在非 DEAD 狀態。
- fix: 在 4.1 CommandDispatcher 介面契約補充建構子簽章：`def __init__(self, session_manager: SessionManager) -> None`；或改用 callback 模式並在介面定義中說明。在 Task #8 描述明確：「CommandDispatcher 初始化時接受 SessionManager 參考，BrokenPipeError 後呼叫 `session_manager.mark_dead(session_id)`」。

---

### [SR-P1-003] P1 - ParsedEvent.event_type 殘留 `status_change`，與 SR-P1-001 修正後的設計矛盾

- id: `SR-P1-003`
- severity: `P1`
- category: `consistency`
- file: `spec section 4.2 / Task #6`
- line: `357`
- rule: 介面定義必須與架構決策一致，不留矛盾語義
- evidence: `ParsedEvent.event_type` 的合法值（行 357）為：`sop_stage | token_update | status_change | text`。但 Task #6 描述（行 504）明確：「Session 狀態判定由 SessionManager 的 stdout reader task 負責（非 OutputParser）。OutputParser 只解析單行內容，不做計時。」。`status_change` 事件類型暗示 OutputParser 可產生狀態變更事件，與「OutputParser 不做狀態判定」的設計矛盾。沒有任何地方定義哪些情況下 OutputParser 應發出 `status_change`（例如，process exit 偵測不在 parse_line 的職責範圍內）。
- impact: 實作者看到 `status_change` 可能在 OutputParser 內自行實作狀態判定邏輯，與 SessionManager 的計時器產生雙重觸發或互相覆蓋，造成 WAIT/RUN 狀態翻轉。
- fix: 從 `ParsedEvent.event_type` 移除 `status_change`，改為 `sop_stage | token_update | text`。若有需要從輸出文字層面判定狀態（例如偵測 claude 的「waiting」prompt 字串），應在 Task #6 描述中明確定義該解析規則的語義和其與 SessionManager 計時器的優先關係。

---

### [SR-P2-001] P2 - Task #8 缺少自動化測試 DoD 條目

- id: `SR-P2-001`
- severity: `P2`
- category: `completeness`
- file: `spec section 5.2 Task #8`
- line: `542-547`
- rule: 核心邏輯任務的 DoD 應要求自動化測試覆蓋，與同層級任務（Task #7）一致
- evidence: Task #8 DoD（行 542-547）有 4 條，全為行為描述，無任何自動化測試條目。Task #8 驗收方式（行 547）：「對執行中的 session 發送指令，觀察 claude 回應」，完全依賴手動驗證。對比 Task #7（同為核心邏輯 L/M 級）DoD 明確要求「自動化測試（mock subprocess）覆蓋 5 個具體路徑」。CommandDispatcher 的 BrokenPipeError 處理和 queue 清理是非同步邏輯，手動難以穩定驗證邊界條件。
- impact: BrokenPipeError 捕捉、queue 清空、consumer task 清理這些關鍵路徑缺乏自動化回歸保護，後續修改容易靜默破壞。
- fix: 在 Task #8 DoD 補充：「自動化測試覆蓋：enqueue 成功路徑、QueueFullError（queue 達 maxsize=50）、BrokenPipeError 捕捉後 crash 流程觸發、session stop 後 queue 清空（舊指令不送入新 session）」。

---

## Summary

- totals: `P0=0, P1=3, P2=1`
- decision: `REJECTED`
