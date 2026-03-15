# Spec Converge Review — Round 1

> engine: fallback (codex 401 Unauthorized)
> scope: spec
> target: dev/specs/claude-session-manager/review/converge/spec-current.md

---

## Findings

### [SR-P1-001] P1 - OutputParser WAIT 狀態判定依賴計時器，但 parse_line 為同步函式，無法偵測「超時無輸出」

- id: `SR-P1-001`
- severity: `P1`
- category: `logic`
- file: `spec section 4.1 / Task #6`
- line: N/A
- rule: 介面契約必須可執行且自洽
- evidence: `OutputParser.parse_line(raw_line: str) -> ParsedEvent | None` 是同步函式，每次只處理一行輸入。但 Task #6 描述「Session 狀態：無輸出超過 N 秒 → WAIT」，這需要計時器/異步監控，parse_line 介面本身無法做到。「N 秒」的值在 spec 中未定義。
- impact: 實作時會發現 WAIT 狀態判定邏輯無處放置，導致要麼塞入 SessionManager（職責越界），要麼重新設計 OutputParser 介面，造成 Task #6 和 Task #7 的邊界模糊。
- fix: 在 spec 中明確：(1) WAIT 狀態判定的責任方（建議由 SessionManager 的 stdout reader task 計時，而非 OutputParser）；(2) 「無輸出 N 秒」的 N 值具體定義（建議 5 秒）；(3) OutputParser 只負責解析單行內容，狀態轉換由外層驅動。

---

### [SR-P1-002] P1 - Task #6 DoD 要求「使用 Wave 0 真實樣本」，但 Wave 0 是 Task #1 的產出，Task #6 的 DoD 驗收在 Wave 0 執行前無法確認

- id: `SR-P1-002`
- severity: `P1`
- category: `completeness`
- file: `spec section 5.2 Task #6`
- line: N/A
- rule: DoD 必須在任務完成時可客觀驗收
- evidence: Task #6 DoD 第三條：「單元測試使用 Wave 0 捕獲的真實輸出樣本」。Task #6 依賴 Task #1（Wave 0）的結論，這在任務清單已正確標記依賴關係。但 DoD 本身隱含：若 Wave 0 是 NO-GO，Task #6 的 DoD 驗收基準完全失效，且 spec 中沒有說明 NO-GO 後 Task #6 的替代 DoD。
- impact: Wave 0 NO-GO 時，Task #6 的驗收標準懸空，實作者無從判斷「完成」條件，增加執行風險。
- fix: 在 Task #6 DoD 補充：「若 Wave 0 結果為 NO-GO，改用備案架構的輸出格式樣本作為測試基準，DoD 第三條改為使用備案架構模擬輸出」。

---

### [SR-P1-003] P1 - CommandDispatcher queue 滿時行為對 TUI 的影響未定義

- id: `SR-P1-003`
- severity: `P1`
- category: `logic`
- file: `spec section 5.2 Task #8 / 4.1`
- line: N/A
- rule: 所有 exception path 必須定義系統行為和用戶回饋
- evidence: Task #8 描述：「queue 滿時 raise QueueFullError」。`CommandDispatcher.enqueue` 的介面契約（4.1）只列出 `SessionNotFoundError` 和 `SessionDeadError`，未包含 `QueueFullError`。此外，整個 spec 中沒有任何地方描述 TUI（app.py 或 Modal）如何處理 `QueueFullError`，也沒有對應的驗收標準（AC-1 到 AC-10 無任何一條涵蓋此情境）。
- impact: QueueFullError 在 TUI 層的處理方式未定義，實作者可能忽略或各自發明處理方式，導致使用者在快速發送指令時遇到靜默失敗或未捕捉例外。
- fix: (1) 在 4.1 CommandDispatcher 介面契約補充 `QueueFullError`；(2) 在 Task #12（app.py）描述中加入 QueueFullError 的 TUI 處理邏輯（顯示警告提示）；(3) 在 AC 或 E1 的處理中補充 queue 滿時的預期用戶體驗。

---

### [SR-P1-004] P1 - SessionState 包含 `cost_usd` 欄位，但 CostAggregator 同樣維護成本，兩者間的同步機制未定義

- id: `SR-P1-004`
- severity: `P1`
- category: `architecture`
- file: `spec section 4.2 / Task #5`
- line: N/A
- rule: 資料所有權必須唯一，避免雙重維護
- evidence: `SessionState` dataclass 有 `tokens_in: int`、`tokens_out: int`、`cost_usd: float` 欄位（4.2）。`CostAggregator`（Task #5）另外維護每個 session 的 token 用量和成本，並提供 `update(session_id, tokens_in, tokens_out, cost_usd)` 和 `get_total()`。Spec 未說明：OutputParser 解析到 token 資訊後，是更新 SessionState 還是 CostAggregator，還是兩者都更新。Session 列表 Widget（Task #9）的 `$（成本）` 欄是讀 SessionState.cost_usd 還是 CostAggregator？
- impact: 實作時成本資料可能在兩處不一致，導致列表顯示的個別成本與狀態列的總成本對不上。
- fix: 明確定義資料流向：建議 SessionState 是單一事實來源（保存個別 session 成本），CostAggregator 只做彙總（從 SessionState 讀取，不獨立儲存）。或反之。在 Data Flow 或 Task #5 描述中明文說明更新順序。

---

### [SR-P1-005] P1 - Task #7 SessionManager 依賴 Task #6 OutputParser，但 Task #6 是大型任務（L），若 Wave 0 延誤會卡住 Task #7

- id: `SR-P1-005`
- severity: `P1`
- category: `completeness`
- file: `spec section 5.1 任務總覽`
- line: N/A
- rule: 關鍵路徑風險必須有緩解措施
- evidence: 依賴鏈：Task #1（Wave 0）→ Task #6（OutputParser L）→ Task #7（SessionManager L）→ Task #8 → Task #12。Wave 0 和 OutputParser 都是關鍵路徑上的重量級任務，且 Wave 0 有明確的 NO-GO 風險。風險章節（Section 8）已列出 Claude CLI PIPE 模式風險，但沒有對應的任務調度緩解措施（例如 Task #7 是否可先用 stub OutputParser 實作）。
- impact: 若 Wave 0 NO-GO 且備案架構評估需時，Task #7、#8、#12 整條 TUI 核心鏈都被卡住，可能造成迭代停滯。
- fix: 在 Task #7 描述中明確：「OutputParser 介面已確定（4.1），Task #7 可先以 stub OutputParser（只回傳 plain_text）並行開發，不需等待 Task #6 完成」。依賴調整為「需要 Task #6 介面定義，不需要 Task #6 完整實作」。

---

### [SR-P2-001] P2 - Task #3 ANSI 正則覆蓋範圍不完整，OSC 序列處理只提及「擴展覆蓋」

- id: `SR-P2-001`
- severity: `P2`
- category: `completeness`
- file: `spec section 5.2 Task #3`
- line: N/A
- rule: 工具庫任務的 DoD 應具體可測試
- evidence: Task #3 描述：「使用正則 `\x1b\[[0-9;]*[a-zA-Z]` 為基礎，擴展覆蓋 OSC 序列」。「擴展覆蓋」是模糊描述，沒有列出需覆蓋的 OSC 模式（如 `\x1b]...\x07` 或 `\x1b]...\x1b\\`）。DoD 只說「覆蓋常見 ANSI escape pattern」，未列舉具體 pattern。
- impact: 單元測試覆蓋範圍因人而異，可能遺漏 claude CLI 實際使用的 OSC 序列，影響 OutputParser 的解析品質。
- fix: 在 Task #3 DoD 補充至少 3 種需測試的 ANSI/OSC pattern（例如：SGR、CSI cursor move、OSC title set），讓測試邊界清楚。

---

### [SR-P2-002] P2 - Task #5 CostSummary 回傳型別未定義

- id: `SR-P2-002`
- severity: `P2`
- category: `completeness`
- file: `spec section 5.2 Task #5`
- line: N/A
- rule: 介面定義必須完整，包含回傳型別
- evidence: Task #5 描述 `get_total() -> CostSummary`，但 `CostSummary` 在整個 spec 中沒有任何定義（4.2 資料模型章節沒有此 class）。
- impact: 實作者需自行決定 CostSummary 的欄位，可能與 TUI 顯示需求不符（例如狀態列需要顯示總 tokens_in/out/cost，但 CostSummary 欄位不明確）。
- fix: 在 4.2 資料模型或 Task #5 描述中補充 `CostSummary` dataclass 的欄位定義（至少：`total_tokens_in: int`、`total_tokens_out: int`、`total_cost_usd: float`）。

---

### [SR-P2-003] P2 - Task #0 DoD 未列出測試框架設定（pytest 或其他）

- id: `SR-P2-003`
- severity: `P2`
- category: `completeness`
- file: `spec section 5.2 Task #0`
- line: N/A
- rule: 基礎建設任務應建立後續任務所需的完整環境
- evidence: Task #0 描述建立 pyproject.toml 和目錄結構，但 DoD 未提及測試框架設定（pytest 依賴、`[tool.pytest.ini_options]` 配置）。後續 Task #2、#3、#4、#5、#6、#7 的 DoD 都需要單元測試，但 spec 從未聲明使用哪個測試框架，也沒有說明 pyproject.toml 是否包含 pytest 作為 dev dependency。
- impact: 各任務實作者可能使用不同測試方式（unittest vs pytest），或測試執行指令不統一。
- fix: 在 Task #0 DoD 補充：「pyproject.toml 包含 pytest 為 dev dependency，`python -m pytest` 可在專案根目錄執行」。

---

## Summary

- totals: `P0=0, P1=5, P2=3`
- decision: `REJECTED`
