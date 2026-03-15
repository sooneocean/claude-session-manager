# Claude Session Manager (CSM)

A terminal UI tool for batch-managing multiple Claude Code sessions from a single dashboard.

## Why

When running 10+ Claude Code sessions simultaneously (e.g., parallel development across projects), you need to constantly alt-tab between terminal windows to check progress, respond to prompts, and track costs. CSM solves this by providing a unified TUI dashboard.

## Features

- **Session lifecycle**: Spawn, stop, restart Claude Code sessions with crash detection
- **Real-time streaming**: See Claude's output as it happens (readline loop + stream-json)
- **SOP stage tracking**: Automatically detects S0-S7 stages from output
- **Cost tracking**: Per-session and total token cost in real-time
- **Command dispatch**: Send prompts to any session from the dashboard
- **Session persistence**: Sessions survive CSM restarts (~/.csm/sessions.json)
- **Filter & Sort**: Filter by status (/ key), sort by cost/stage/status (S key)
- **Session naming**: Label sessions for easy identification

## Architecture

```
CSM uses claude -p --resume --output-format stream-json mode.
Each interaction is an independent short-lived process (not a long-running subprocess).

TUI Layer (Textual)          Core Layer (asyncio)         External
+------------------+        +--------------------+       +----------+
| SessionList      |<------>| SessionManager     |<----->| claude   |
| DetailPanel      |        | OutputParser (JSON) |       | CLI      |
| Modals           |        | CommandDispatcher  |       | process  |
| StatusBar        |        | CostAggregator     |       +----------+
+------------------+        +--------------------+
```

## Install

```bash
git clone https://github.com/sooneocean/claude-session-manager.git
cd claude-session-manager
pip install -e ".[dev]"
```

### Requirements

- Python 3.10+
- `claude` CLI installed and in PATH
- Windows Terminal recommended (not Git Bash/mintty)

## Usage

```bash
python -m csm    # or: csm
```

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `N` | New session (specify directory, name, resume ID, model) |
| `Enter` | Send command to selected session |
| `X` | Stop selected session |
| `R` | Restart selected session |
| `/` | Cycle filter (All / RUN / WAIT / DEAD / DONE) |
| `S` | Cycle sort (None / Cost / Status / Stage) |
| `Q` | Quit (saves sessions) |

### Dashboard Layout

```
+------------------------------------------------------------------+
| Claude Session Manager                Total: $12.34  Sessions: 8 |
+--------------------------------------+---------------------------+
| # | Name       | Stage | Status | $  | Recent Output             |
|---+------------+-------+--------+----|                           |
| 1 | project-a  |  S4   | RUN    |2.1 | Implementing wave 1...    |
| 2 | api-server |  S0   | WAIT   |0.3 | Waiting for confirmation  |
| 3 | frontend   |  S6   | RUN    |4.2 | Running test suite...     |
+--------------------------------------+---------------------------+
| [N]ew [X]Stop [R]estart [Enter]Cmd [/]Filter [S]ort [Q]uit      |
+------------------------------------------------------------------+
```

## Development

```bash
# Run tests
python -m pytest tests/ -v

# Current: 135 tests passing
```

## How It Works

1. **Spawn**: Runs `claude -p --output-format stream-json --verbose --include-partial-messages "prompt"` as a subprocess
2. **Stream**: Reads stdout line-by-line, parsing JSON events in real-time
3. **Resume**: Subsequent commands use `--resume SESSION_ID` to continue the conversation
4. **Display**: Textual TUI renders session list + detail panel, refreshed every 1 second

## License

MIT
