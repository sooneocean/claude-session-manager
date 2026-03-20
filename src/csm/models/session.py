"""Session data models for Claude Session Manager."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid


class SessionStatus(Enum):
    STARTING = "STARTING"
    RUN = "RUN"    # Process currently executing
    WAIT = "WAIT"  # Waiting for user input (last --print call completed)
    DONE = "DONE"  # Session completed normally
    DEAD = "DEAD"  # Process crashed


@dataclass
class SessionConfig:
    cwd: str
    resume_id: str | None = None
    model: str | None = None
    permission_mode: str = "auto"
    name: str | None = None
    max_budget_usd: float | None = None


@dataclass
class SessionState:
    session_id: str
    config: SessionConfig
    claude_session_id: str | None = None  # Claude CLI's session ID (for --resume)
    status: SessionStatus = SessionStatus.STARTING
    sop_stage: str | None = None
    exit_code: int | None = None
    pid: int | None = None
    started_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    last_result: str = ""  # Most recent response text
    notes: str = ""  # User-defined notes/annotations
    tags: list[str] = field(default_factory=list)  # User-defined tags

    @staticmethod
    def create(config: SessionConfig) -> "SessionState":
        return SessionState(
            session_id=str(uuid.uuid4()),
            config=config,
        )
