# Spec Converge Review — Round 4

> engine: fallback (codex exit code 2 — unexpected argument)
> scope: spec
> target: dev/specs/claude-session-manager/review/converge/spec-current.md

---

## 前輪修正驗證摘要

| Finding ID | 修正項目 | 驗證結果 |
|-----------|---------|---------|
| R3-SR-P1-001 | Task #13 DoD 改為「手動測試清單覆蓋 10 個驗收標準（AC-1 至 AC-10）」 | 已確認（行 633） |
| R3-SR-P1-002 | CommandDispatcher notify_crash 跨元件介面定義 | 未修正（見下） |
| R3-SR-P1-003 | ParsedEvent.event_type 移除 status_change | 部分修正（dataclass 行 357 已正確，但 OutputParser docstring 行 312 殘留舊值） |
| R3-SR-P2-001 | Task #8 加入自動化測試 DoD 條目 | 已確認（行 547） |

---

## Findings

### [SR-P1-001] P1 - CommandDispatcher 與 SessionManager 的耦合機制仍未定義

- id: `SR-P1-001`
- severity: `P1`
- category: `architecture`
- file: `spec section 4.1 CommandDispatcher / Task #8`
- line: `300-304`（介面契約）、`241`（Data Flow）、`541-548`（Task #8）
- rule: 跨元件呼叫的介面契約必須完整定義，包含依賴注入方式
- evidence: R3 要求在 4.1 或 Task #8 補充 CommandDispatcher 如何持有 SessionManager 參考（建構子注入或 callback）。驗證 spec-current.md：行 300-304 的 CommandDispatcher 介面契約仍只有 `enqueue` 方法，無建構子簽章；行 241 Data Flow 仍寫 `CP->>SM: session_manager.get_session(id).status checked → DEAD`，用 `get_session` 讀取狀態而非主動回報，且未說明 CP 如何取得 SM 參考；行 541-548 Task #8 描述仍只說「觸發 crash 流程」，無具體實作路徑。
- impact: 實作者面對兩種可能：(1) CommandDispatcher 持有 SessionManager 參考並呼叫其方法；(2) CommandDispatcher 用 callback 通知外層。兩者耦合方向相反，任何一種實作都無 spec 依據，且可能與 Task #12 app.py 的初始化順序衝突（循環依賴）。
- fix: 在 4.1 CommandDispatcher 介面契約補充建構子：`def __init__(self, session_manager: SessionManager) -> None`；在 Task #8 描述明確：「CommandDispatcher 初始化時接受 SessionManager 參考，BrokenPipeError 後呼叫 `session_manager.mark_dead(session_id)` 通知 crash」。

---

### [SR-P2-001] P2 - OutputParser docstring 殘留 status_change 和 plain_text，與 ParsedEvent 定義矛盾

- id: `SR-P2-001`
- severity: `P2`
- category: `consistency`
- file: `spec section 4.1 OutputParser`
- line: `312`
- rule: 介面定義各處描述必須一致
- evidence: 行 357 的 `ParsedEvent.event_type` 已正確改為 `sop_stage | token_update | text`（R3-SR-P1-003 修正）。但行 312 OutputParser.parse_line 的 docstring 仍寫：「回傳 ParsedEvent (sop_stage_change | token_update | status_change | plain_text)」，殘留了 `status_change`（已廢棄）和 `plain_text`（已改為 `text`），且用 `sop_stage_change` 而非 `sop_stage`，三處命名全部不一致。
- impact: 實作者若以 docstring 為準，會實作 `status_change` 事件類型，與 dataclass 定義矛盾，在 runtime 出現 `ValueError` 或靜默邏輯錯誤。
- fix: 將行 312 docstring 改為：「回傳 ParsedEvent (sop_stage | token_update | text) 或 None（無法辨識的行）」。

---

## Summary

- totals: `P0=0, P1=1, P2=1`
- decision: `REJECTED`
