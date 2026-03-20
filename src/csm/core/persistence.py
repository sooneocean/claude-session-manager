"""Session persistence - save/load session state to JSON file."""
import json
import logging
from pathlib import Path

from csm.models.session import SessionState, SessionConfig, SessionStatus

logger = logging.getLogger(__name__)

DEFAULT_SESSIONS_PATH = Path.home() / ".csm" / "sessions.json"


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
    return state


def save_sessions(
    sessions: list[SessionState],
    path: Path = DEFAULT_SESSIONS_PATH,
) -> None:
    """Save session states to a JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [_serialize_session(s) for s in sessions]
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
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
