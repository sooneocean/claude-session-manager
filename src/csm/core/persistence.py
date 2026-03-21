"""Session persistence - save/load session state to JSON file."""
import json
import logging
from pathlib import Path

from csm.models.session import SessionState, SessionConfig, SessionStatus

logger = logging.getLogger(__name__)

DEFAULT_SESSIONS_PATH = Path.home() / ".csm" / "sessions.json"
DEFAULT_LOGS_DIR = Path.home() / ".csm" / "logs"


def _serialize_session(state: SessionState) -> dict:
    """Convert a SessionState to a JSON-serializable dict."""
    return {
        "session_id": state.session_id,
        "config": {
            "cwd": state.config.cwd,
            "resume_id": state.config.resume_id,
            "model": state.config.model,
            "permission_mode": state.config.permission_mode,
            "name": state.config.name,
            "max_budget_usd": state.config.max_budget_usd,
        },
        "claude_session_id": state.claude_session_id,
        "status": state.status.value,
        "sop_stage": state.sop_stage,
        "tokens_in": state.tokens_in,
        "tokens_out": state.tokens_out,
        "cost_usd": state.cost_usd,
        "last_result": state.last_result,
        "notes": state.notes,
        "tags": state.tags,
        "command_history": state.command_history[-50:],  # Keep last 50
        "total_active_seconds": state.total_active_seconds,
        "pinned": state.pinned,
        "color": state.color,
        "started_at": state.started_at.isoformat(),
        "last_activity": state.last_activity.isoformat(),
    }


def _deserialize_session(data: dict) -> SessionState:
    """Reconstruct a SessionState from a dict."""
    config = SessionConfig(
        cwd=data["config"]["cwd"],
        resume_id=data["config"].get("resume_id"),
        model=data["config"].get("model"),
        permission_mode=data["config"].get("permission_mode", "auto"),
        name=data["config"].get("name"),
        max_budget_usd=data["config"].get("max_budget_usd"),
    )
    state = SessionState(
        session_id=data["session_id"],
        config=config,
    )
    state.claude_session_id = data.get("claude_session_id")
    state.status = SessionStatus(data.get("status", "WAIT"))
    state.sop_stage = data.get("sop_stage")
    state.tokens_in = data.get("tokens_in", 0)
    state.tokens_out = data.get("tokens_out", 0)
    state.cost_usd = data.get("cost_usd", 0.0)
    state.last_result = data.get("last_result", "")
    state.notes = data.get("notes", "")
    state.tags = data.get("tags", [])
    state.command_history = data.get("command_history", [])
    state.total_active_seconds = data.get("total_active_seconds", 0.0)
    state.pinned = data.get("pinned", False)
    state.color = data.get("color", "")
    if data.get("started_at"):
        try:
            from datetime import datetime
            state.started_at = datetime.fromisoformat(data["started_at"])
        except (ValueError, TypeError):
            pass
    if data.get("last_activity"):
        try:
            from datetime import datetime
            state.last_activity = datetime.fromisoformat(data["last_activity"])
        except (ValueError, TypeError):
            pass
    return state


def save_sessions(
    sessions: list[SessionState],
    path: Path = DEFAULT_SESSIONS_PATH,
) -> None:
    """Save session states to a JSON file (atomic write via temp file)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [_serialize_session(s) for s in sessions]
    content = json.dumps(data, indent=2, ensure_ascii=False)
    # Atomic write: write to temp file then rename
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)
    logger.info("Saved %d sessions to %s", len(sessions), path)


def load_sessions(
    path: Path = DEFAULT_SESSIONS_PATH,
) -> list[SessionState]:
    """Load session states from a JSON file.
    Returns empty list if file doesn't exist or is corrupt."""
    path = Path(path)
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, list):
            return []
        return [_deserialize_session(entry) for entry in data]
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning("Failed to load sessions from %s: %s", path, e)
        return []


# ------------------------------------------------------------------
# Log persistence — save/load per-session output buffer lines
# ------------------------------------------------------------------

def save_session_logs(
    session_id: str,
    lines: list[str],
    logs_dir: Path = DEFAULT_LOGS_DIR,
) -> None:
    """Save a session's output buffer lines to a JSON file."""
    logs_dir = Path(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    filepath = logs_dir / f"{session_id}.json"
    filepath.write_text(json.dumps(lines, ensure_ascii=False), encoding="utf-8")


def load_session_logs(
    session_id: str,
    logs_dir: Path = DEFAULT_LOGS_DIR,
) -> list[str]:
    """Load a session's saved output buffer lines. Returns empty list if not found."""
    filepath = Path(logs_dir) / f"{session_id}.json"
    if not filepath.exists():
        return []
    try:
        raw = filepath.read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, ValueError):
        return []


def delete_session_logs(
    session_id: str,
    logs_dir: Path = DEFAULT_LOGS_DIR,
) -> None:
    """Remove a session's saved log file."""
    filepath = Path(logs_dir) / f"{session_id}.json"
    filepath.unlink(missing_ok=True)


def export_backup(
    sessions: list[SessionState],
    buffer_store,
    filepath: Path,
) -> None:
    """Export all sessions + logs to a single backup JSON file."""
    backup = {
        "version": 1,
        "sessions": [_serialize_session(s) for s in sessions],
        "logs": {},
    }
    for s in sessions:
        buf = buffer_store.get(s.session_id)
        if buf is not None:
            backup["logs"][s.session_id] = buf.get_lines()
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(json.dumps(backup, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Exported backup with %d sessions to %s", len(sessions), filepath)


def import_backup(filepath: Path) -> tuple[list[SessionState], dict[str, list[str]]]:
    """Import sessions + logs from a backup file.
    Returns (sessions, {session_id: [lines]})."""
    filepath = Path(filepath)
    raw = filepath.read_text(encoding="utf-8")
    data = json.loads(raw)
    sessions = [_deserialize_session(entry) for entry in data.get("sessions", [])]
    logs = data.get("logs", {})
    return sessions, logs


def save_view_state(
    filter_status: str | None,
    sort_key: str,
    path: Path | None = None,
) -> None:
    """Save current filter/sort state."""
    if path is None:
        path = Path.home() / ".csm" / "view_state.json"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"filter_status": filter_status, "sort_key": sort_key}
    path.write_text(json.dumps(data), encoding="utf-8")


def load_view_state(
    path: Path | None = None,
) -> tuple[str | None, str]:
    """Load saved filter/sort state. Returns (filter_status, sort_key)."""
    if path is None:
        path = Path.home() / ".csm" / "view_state.json"
    path = Path(path)
    if not path.exists():
        return None, "none"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("filter_status"), data.get("sort_key", "none")
    except (json.JSONDecodeError, ValueError):
        return None, "none"


def cleanup_orphan_logs(
    active_session_ids: set[str],
    logs_dir: Path = DEFAULT_LOGS_DIR,
    max_age_days: int = 7,
) -> int:
    """Remove log files that don't belong to active sessions and are older than max_age_days.
    Returns number of files removed."""
    logs_dir = Path(logs_dir)
    if not logs_dir.exists():
        return 0
    import time
    now = time.time()
    removed = 0
    for f in logs_dir.glob("*.json"):
        session_id = f.stem
        if session_id in active_session_ids:
            continue
        age_days = (now - f.stat().st_mtime) / 86400
        if age_days > max_age_days:
            f.unlink(missing_ok=True)
            removed += 1
    return removed
