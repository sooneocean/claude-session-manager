# Changelog

All notable changes to Claude Session Manager (CSM) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v0.5.0] - 2026-03-15

### Added
- Session naming support (`--name` flag, display in dashboard)
- README.md with install instructions, architecture, and usage guide

### Changed
- dev_spec updated to match actual implementation (stream-json architecture)
- SessionList column "Directory" renamed to "Name" (shows name or dir basename)
- NewSessionModal now includes name input field

## [v0.4.0] - 2026-03-15

### Added
- `/iterate` skill for automated product iteration (scan → propose → autopilot → release)
- CHANGELOG.md and iterate-history.json

## [v0.3.0] - 2026-03-15

### Added
- Real-time streaming output in detail panel (readline loop replaces communicate())
- `--include-partial-messages` flag for mid-stream assistant content
- Session persistence across CSM restarts (~/.csm/sessions.json)
- Filter sessions by status (/ key: cycle RUN/WAIT/DEAD/DONE/All)
- Sort sessions by cost/status/stage (S key)

### Changed
- DetailPanel uses incremental append (no full redraw on refresh)
- SessionList uses differential update (preserves cursor position)
- ParsedEvent split into typed subclasses (ResultEvent, AssistantEvent, InitEvent)
- Removed dead code (add_state_change_callback)

## [v0.1.0] - 2026-03-15

### Added
- Initial CSM TUI tool (Python/Textual)
- Session lifecycle management (spawn, stop, restart, crash detection)
- Dashboard with session list + detail panel + status bar
- Command dispatch to sessions via `claude -p --resume --output-format stream-json`
- SOP stage detection (S0-S7) from stream-json output
- Token cost tracking with per-session and total aggregation
- Output buffering with RingBuffer (1000 lines)
- Modal dialogs (NewSession, ConfirmStop, CommandInput, RunningWarning)
- Keyboard shortcuts (N/X/R/Enter/Q/S//)
