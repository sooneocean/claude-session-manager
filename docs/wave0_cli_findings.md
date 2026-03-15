# Wave 0: Claude CLI PIPE Mode Findings

> **Decision**: GO (with architecture modification)
> **Date**: 2026-03-15

## Test Results

| Test | Result | Details |
|------|--------|---------|
| PIPE spawn (`--print --json`) | PASS | claude CLI exits 0, returns JSON output |
| Interactive PIPE | FAIL | Interactive mode stdout doesn't output to PIPE (readline returns 0 lines after 30s timeout). Process stays alive but stdout is silent. |
| stream-json (`--print --verbose`) | PASS | Returns structured JSON lines: system/init, assistant, rate_limit_event, result |
| `--resume` in `--print` mode | PASS | Session can be created and resumed. Resumed session correctly recalls context. |

## Key Findings

### 1. Interactive mode does NOT work with PIPE

When spawning `claude` (without `--print`) with `stdin=PIPE, stdout=PIPE`:
- Process starts and stays alive
- But stdout.readline() returns nothing (times out)
- Claude CLI likely detects `isatty(stdout) == False` and buffers/suppresses output
- **Conclusion**: Cannot use long-running interactive subprocess approach

### 2. `--print --output-format stream-json` works perfectly

Each line is a JSON object with `type` field:

```json
{"type":"system","subtype":"init","session_id":"...","model":"claude-opus-4-6[1m]",...}
{"type":"system","subtype":"hook_started",...}
{"type":"system","subtype":"hook_response",...}
{"type":"assistant","message":{"content":[{"type":"text","text":"..."}],"usage":{...}},...}
{"type":"rate_limit_event",...}
{"type":"result","total_cost_usd":0.058,"usage":{"input_tokens":3,"output_tokens":4},...}
```

### 3. Cost/Token data is precise

From `result` event:
- `total_cost_usd`: exact cost in USD
- `usage.input_tokens`: input token count
- `usage.output_tokens`: output token count
- `modelUsage`: per-model breakdown with `costUSD`

### 4. `--resume` enables multi-turn conversations

- First call creates a session with a `session_id`
- Subsequent calls with `--resume SESSION_ID` continue the conversation
- Context is preserved (tested: "remember 42" → resume → "what number?" → "42")

## Architecture Decision

**Original plan**: Long-running interactive subprocess with stdout parsing

**Revised plan**: Series of `claude -p --resume --output-format stream-json --verbose` calls

Each "session" in CSM:
1. First prompt: `claude -p --output-format stream-json --verbose "prompt"` → get session_id
2. Follow-up: `claude -p --resume SESSION_ID --output-format stream-json --verbose "prompt"`
3. Each call is a short-lived process (runs, responds, exits)
4. JSON output gives us structured data (no regex parsing needed)

### Impact on Tasks

| Task | Original | Revised |
|------|----------|---------|
| T3 (ANSI strip) | Full ANSI parser | Minimal — only for `result.result` text if needed |
| T6 (OutputParser) | Regex + state machine on raw stdout | JSON line parser (trivial) |
| T7 (SessionManager) | Long-running subprocess manager | Per-request process spawner + session_id tracking |
| T8 (CommandDispatcher) | stdin.write + asyncio.Queue | Spawn new `claude -p --resume` process per command |
| E1 (concurrent commands) | FIFO Queue for stdin | Sequential spawning (one at a time per session) |
| E2 (BrokenPipeError) | stdin.write exception handling | Process exit code handling (simpler) |
| "Waiting for input" detection | Timeout-based stdout monitoring | Not needed — each call is request-response |
