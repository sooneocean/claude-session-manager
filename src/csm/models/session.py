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
    command_history: list[str] = field(default_factory=list)  # Recent commands sent
    total_active_seconds: float = 0.0  # Accumulated RUN-state time
    pinned: bool = False  # Pin session to top of list
    color: str = ""  # User-defined color label (e.g. "red", "green", "blue")
    _run_started: datetime | None = field(default=None, repr=False)  # Internal: when last RUN started

    @staticmethod
    def create(config: SessionConfig) -> "SessionState":
        return SessionState(
            session_id=str(uuid.uuid4()),
            config=config,
        )

    def track_run_start(self) -> None:
        """Mark the start of a RUN period for duration tracking."""
        self._run_started = datetime.now()

    def track_run_end(self) -> None:
        """Accumulate elapsed RUN time when transitioning out of RUN."""
        if self._run_started is not None:
            elapsed = (datetime.now() - self._run_started).total_seconds()
            self.total_active_seconds += max(0, elapsed)
            self._run_started = None

    @property
    def cost_per_hour(self) -> float:
        """Calculate cost rate in $/hr based on active duration."""
        total_secs = self.total_active_seconds
        if self._run_started:
            total_secs += max(0, (datetime.now() - self._run_started).total_seconds())
        if total_secs < 60:  # Need at least 1 min of data
            return 0.0
        return (self.cost_usd / total_secs) * 3600

    @property
    def active_duration_str(self) -> str:
        """Human-readable total active (RUN) duration."""
        secs = int(self.total_active_seconds)
        if self._run_started:
            secs += max(0, int((datetime.now() - self._run_started).total_seconds()))
        if secs < 60:
            return f"{secs}s"
        elif secs < 3600:
            return f"{secs // 60}m {secs % 60}s"
        h, rem = divmod(secs, 3600)
        return f"{h}h {rem // 60}m"
