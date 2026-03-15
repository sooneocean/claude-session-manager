# Claude Session Manager (CSM)

> A Python TUI tool that lets you manage 10+ Claude Code sessions from a single terminal dashboard.

[![v0.9.0](https://img.shields.io/badge/version-v0.9.0-blue)](https://github.com/sooneocean/claude-session-manager/releases/tag/v0.9.0)
[![Tests](https://img.shields.io/badge/tests-150%20passing-green)]()
[![Python](https://img.shields.io/badge/python-3.10+-yellow)]()
[![License: MIT](https://img.shields.io/badge/license-MIT-lightgrey)]()

---

## The Problem

You're running 10+ Claude Code sessions across different projects. Each is in a separate terminal window. You're constantly alt-tabbing to:

- Check which sessions need your input
- See how much each session costs
- Track which SOP stage (S0-S7) each is in
- Send commands to specific sessions

**CSM puts all of that in one screen.**

## Quick Start

```bash
# 1. Clone
git clone https://github.com/sooneocean/claude-session-manager.git
cd claude-session-manager

# 2. Install
pip install -e .

# 3. Run
python -m csm
```

First launch shows a welcome screen. Press **N** to create your first session.

### Prerequisites

| Requirement | Why |
|-------------|-----|
| Python 3.10+ | asyncio features, union types |
| `claude` CLI in PATH | CSM spawns claude processes |
| Windows Terminal (recommended) | Textual rendering; avoid Git Bash/mintty |

### Optional

```bash
pip install -e ".[monitor]"   # psutil - CPU/RAM monitoring in status bar
pip install -e ".[web]"       # textual-serve - browser-based dashboard
pip install -e ".[dev]"       # pytest - run test suite
```

---

## How It Works

```
                    You
                     |
              +------v------+
              |   CSM TUI   |  <-- one terminal, all sessions
              +------+------+
                     |
         +-----------+-----------+
         |           |           |
    +----v----+ +----v----+ +----v----+
    | claude  | | claude  | | claude  |  <-- each is a short-lived process
    | -p      | | -p      | | -p      |
    | --resume| | --resume| | --resume|
    | proj-a  | | proj-b  | | proj-c  |
    +---------+ +---------+ +---------+
```

Each "session" is **not** a long-running subprocess. Instead:

1. **Spawn**: `claude -p --output-format stream-json --verbose --include-partial-messages "prompt"`
2. **Stream**: CSM reads stdout line-by-line, parsing JSON events in real-time
3. **Resume**: Next command uses `--resume SESSION_ID` to continue the conversation
4. **Persist**: Session state saves to `~/.csm/sessions.json` on quit

This design was discovered during [Wave 0 validation](docs/wave0_cli_findings.md) — interactive subprocess mode doesn't work because claude CLI suppresses output when `isatty()` is false.

---

## Dashboard

```
+------------------------------------------------------------------+
| Claude Session Manager        Total: $12.34 | Sessions: 3/3     |
|                                CPU: 45% RAM: 62%                 |
+--------------------------------------+---------------------------+
| # | Name       | Stage | Status | $  | Recent Output             |
|---+------------+-------+--------+----|                           |
| 1 | project-a  |  S4   | RUN    |2.1 | Implementing wave 1...    |
| 2 | api-server |  S0   | WAIT   |0.3 | Waiting for confirmation  |
| 3 | frontend   |  S6   | RUN    |4.2 | Running test suite...     |
+--------------------------------------+---------------------------+
| [N]ew [X]Stop [R]estart [Enter]Cmd [B]roadcast [H]elp [Q]uit    |
+------------------------------------------------------------------+
```

### Keyboard Shortcuts

| Key | What it does |
|-----|-------------|
| **N** | Create new session — enter project directory, optional name/model/resume ID |
| **Enter** | Send a command to the selected session (warns if session is busy) |
| **X** | Stop selected session (with confirmation) |
| **R** | Restart a stopped/crashed session with same config |
| **B** | Broadcast — send the same command to ALL waiting sessions (e.g., `/compact`) |
| **/** | Filter sessions by status: cycle through All → RUN → WAIT → DEAD → DONE |
| **S** | Sort sessions: cycle through None → Cost → Status → Stage |
| **H** | Help screen with all shortcuts and session state explanations |
| **Q** | Quit — automatically saves all sessions to disk |

### Session States

| State | Meaning | Color |
|-------|---------|-------|
| **RUN** | Claude is processing a command | Green |
| **WAIT** | Ready for your next command | Yellow |
| **DEAD** | Process crashed (press R to restart) | Red |
| **DONE** | Session stopped normally | Gray |

---

## Features

### Real-time Streaming
Output appears in the detail panel as Claude generates it — not after the full response completes. Uses `--include-partial-messages` for mid-stream content.

### Cost Tracking
Each session shows its accumulated cost. Status bar shows total across all sessions. Data comes directly from claude CLI's structured JSON output (precise, not estimated).

### SOP Stage Detection
If a session is running an SDD SOP pipeline, CSM detects the current stage (S0-S7) from output patterns like `Launching skill: s4-implement`.

### Auto-Compact
When a session's token usage exceeds 50K (input + output combined), CSM automatically sends `/compact` and resets the counter. Prevents context window overflow.

### Session Persistence
Sessions are saved to `~/.csm/sessions.json` on quit. Next time you start CSM, they're restored automatically with a notification.

### System Monitoring
With `psutil` installed, the status bar shows CPU and RAM usage. Displays **HIGH LOAD** warning when CPU > 90% or RAM > 80%.

### Web Mode
Access CSM from a browser with zero code changes:

```bash
pip install textual-serve
textual serve "python -m csm"
# Opens http://localhost:8566
```

---

## Project Structure

```
src/csm/
├── app.py                      # Textual App — layout, keybindings, refresh loop
├── __main__.py                 # python -m csm entry point
├── core/
│   ├── session_manager.py      # Spawn/stop/restart sessions, auto-compact
│   ├── output_parser.py        # Parse stream-json lines into typed events
│   ├── command_dispatcher.py   # FIFO queue per session, async consumer
│   └── persistence.py          # Save/load sessions to ~/.csm/sessions.json
├── models/
│   ├── session.py              # SessionState, SessionConfig, SessionStatus
│   └── cost.py                 # CostAggregator, CostSummary
├── widgets/
│   ├── session_list.py         # DataTable with filter/sort/differential update
│   ├── detail_panel.py         # RichLog with incremental streaming
│   └── modals.py               # NewSession, ConfirmStop, CommandInput,
│                               # RunningWarning, Welcome, Help
├── utils/
│   ├── ring_buffer.py          # Fixed-capacity deque wrapper (1000 lines)
│   └── ansi.py                 # Strip ANSI escapes + CR overwrite
└── styles/
    └── app.tcss                # Textual CSS layout

tests/                          # 150 tests (pytest + pytest-asyncio)
├── test_session_manager.py     # 27 tests — spawn, stop, restart, crash, retry
├── test_output_parser.py       # 18 tests — JSON parsing, SOP detection
├── test_command_dispatcher.py  # 15 tests — queue, FIFO, cleanup
├── test_integration.py         # 8 tests  — full lifecycle scenarios
├── test_app.py                 # 8 tests  — TUI keybindings, layout
├── ...and 10 more test files
```

---

## For AI Agents

If you're an AI agent reading this repo, here's what you need to know:

### Key Design Decisions

1. **No interactive subprocess** — claude CLI detects `isatty()` and won't output to piped stdout. We use `--print --resume --output-format stream-json` instead. See [Wave 0 findings](docs/wave0_cli_findings.md).

2. **Short-lived processes** — each `send_command()` spawns a new `claude -p` process. No long-running subprocess management needed.

3. **Retry on failure** — failed claude calls retry once before marking session DEAD.

4. **Output parsing is trivial** — stream-json gives structured JSON lines. `OutputParser` returns typed dataclasses (`ResultEvent`, `AssistantEvent`, `InitEvent`), not regex matches.

### How to Modify

| Want to... | Change... |
|-----------|-----------|
| Add a new keybinding | `app.py` BINDINGS list + action method |
| Add a new modal | `widgets/modals.py` — extend `ModalScreen` |
| Change session behavior | `core/session_manager.py` — `spawn()`, `send_command()`, `_run_claude()` |
| Add a new parsed event type | `core/output_parser.py` — add dataclass + handler in `parse_line()` |
| Change persistence format | `core/persistence.py` — `_serialize_session()` / `_deserialize_session()` |

### Running Tests

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v          # all 150 tests
python -m pytest tests/ -k "spawn"  # filter by name
```

### Constants

| Constant | Value | Location |
|----------|-------|----------|
| `SESSION_LIMIT` | 20 | `session_manager.py` |
| `AUTO_COMPACT_TOKEN_THRESHOLD` | 50,000 | `session_manager.py` |
| `QUEUE_MAX_SIZE` | 50 | `command_dispatcher.py` |
| `RingBuffer default capacity` | 1,000 lines | `ring_buffer.py` |
| `Process timeout` | 600s (10 min) | `session_manager.py` |
| `Stop terminate timeout` | 5s | `session_manager.py` |

---

## Version History

| Version | Date | Highlights |
|---------|------|-----------|
| v0.9.0 | 2026-03-15 | Auto-compact at 50K tokens |
| v0.8.0 | 2026-03-15 | Welcome screen, empty state guidance |
| v0.7.0 | 2026-03-15 | psutil monitoring, retry mechanism |
| v0.6.0 | 2026-03-15 | Help screen, broadcast command |
| v0.5.0 | 2026-03-15 | Session naming, README |
| v0.4.0 | 2026-03-15 | /iterate skill for automated iteration |
| v0.3.0 | 2026-03-15 | Real-time streaming output |
| v0.2.0 | 2026-03-15 | Quality refactor, persistence |
| v0.1.0 | 2026-03-15 | Initial release |

Full changelog: [CHANGELOG.md](CHANGELOG.md)

---

## Built With

This project was built entirely by Claude Code using the [SDD Framework](https://github.com/anthropics/claude-code) — a structured development workflow with:

- **S0-S7 SOP pipeline**: requirement → analysis → spec review → planning → implementation → code review → testing → commit
- **TDD**: 150 tests written before implementation (RED → GREEN → REFACTOR)
- **Adversarial review**: R1 challenger → R2 defender → R3 judge
- **Spec convergence**: 5-round iterative review loop
- **Automated iteration**: `/iterate` skill scans for improvements, proposes features, implements via `/autopilot`, and creates GitHub releases

From zero to v0.9.0 in one conversation session.

## License

MIT
