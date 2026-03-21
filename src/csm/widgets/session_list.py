"""SessionList widget - DataTable showing all sessions. T9 + v2 refactor"""
import os
from datetime import datetime
from enum import Enum

from rich.text import Text
from textual.widgets import DataTable
from textual.message import Message

from csm.models.session import SessionState, SessionStatus


class SortKey(Enum):
    """Available sort keys for the session list."""
    NONE = "none"
    COST = "cost"
    STAGE = "stage"
    STATUS = "status"


class SessionList(DataTable):
    """Session list widget showing all sessions in a table."""

    class SessionSelected(Message):
        """Posted when the selected session row changes."""

        def __init__(self, session_id: str | None) -> None:
            super().__init__()
            self.session_id = session_id

    STATUS_DISPLAY: dict[SessionStatus, tuple[str, str]] = {
        SessionStatus.STARTING: ("INIT", "yellow"),
        SessionStatus.RUN: ("RUN", "green"),
        SessionStatus.WAIT: ("WAIT", "yellow"),
        SessionStatus.DONE: ("DONE", "dim"),
        SessionStatus.DEAD: ("DEAD", "red"),
    }

    STATUS_ORDER = {
        SessionStatus.RUN: 0,
        SessionStatus.WAIT: 1,
        SessionStatus.STARTING: 2,
        SessionStatus.DEAD: 3,
        SessionStatus.DONE: 4,
    }

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._filter_status: SessionStatus | None = None
        self._filter_tag: str | None = None
        self._sort_key: SortKey = SortKey.NONE
        self._all_sessions: list[SessionState] = []

    def on_mount(self) -> None:
        self.add_columns("#", "Name", "Status", "Stage", "Cost($)", "Tokens", "Uptime")
        self.cursor_type = "row"

    @staticmethod
    def _format_status(status: SessionStatus) -> Text:
        """Return a Rich Text object with colored status label."""
        label, color = SessionList.STATUS_DISPLAY.get(status, ("?", "white"))
        return Text(label, style=color)

    @staticmethod
    def _format_tokens(tokens_in: int, tokens_out: int) -> str:
        """Format token counts compactly (e.g. '12.5k/6.2k')."""
        def _fmt(n: int) -> str:
            if n >= 1000:
                return f"{n / 1000:.1f}k"
            return str(n)
        return f"{_fmt(tokens_in)}/{_fmt(tokens_out)}"

    @staticmethod
    def _format_uptime(started_at: datetime, status: SessionStatus) -> str:
        """Format elapsed time since session started (e.g. '2h 15m')."""
        if status in (SessionStatus.DONE, SessionStatus.DEAD):
            return "--"
        delta = datetime.now() - started_at
        secs = max(0, int(delta.total_seconds()))
        if secs < 60:
            return f"{secs}s"
        elif secs < 3600:
            return f"{secs // 60}m {secs % 60}s"
        elif secs < 86400:
            h, rem = divmod(secs, 3600)
            return f"{h}h {rem // 60}m"
        d, rem = divmod(secs, 86400)
        return f"{d}d {rem // 3600}h"

    def _build_row(self, idx: int, s: SessionState) -> tuple:
        """Build a row tuple for a session."""
        display_name = s.config.name or os.path.basename(s.config.cwd) or s.config.cwd
        pin_marker = "* " if s.pinned else ""
        return (
            str(idx),
            f"{pin_marker}{display_name}",
            self._format_status(s.status),
            s.sop_stage or "--",
            f"{s.cost_usd:.2f}",
            self._format_tokens(s.tokens_in, s.tokens_out),
            self._format_uptime(s.started_at, s.status),
        )

    def update_sessions(self, sessions: list[SessionState]) -> None:
        """Refresh the table with current session data using differential update."""
        self._all_sessions = sessions
        filtered = self._apply_filter(sessions)
        sorted_sessions = self._apply_sort(filtered)

        # Show guidance when empty (only if columns are initialized)
        if not sorted_sessions:
            if self.columns and not self.rows:
                self.add_row("", "Press N to create first session", "", "", "", "", "", key="__empty__")
            return
        # Remove empty placeholder if sessions exist
        if self.rows:
            existing = [str(rk.value) for rk in self.rows.keys()]
            if "__empty__" in existing:
                self.remove_row("__empty__")

        # Remember current cursor position
        try:
            current_cursor_row = self.cursor_row
        except Exception:
            current_cursor_row = 0

        # Build desired rows
        desired_keys = [s.session_id for s in sorted_sessions]
        existing_keys = [str(rk.value) for rk in self.rows.keys()] if self.rows else []

        # If structure changed, full rebuild; otherwise update in-place
        if desired_keys != existing_keys:
            self.clear()
            for i, s in enumerate(sorted_sessions, 1):
                self.add_row(*self._build_row(i, s), key=s.session_id)
            # Restore cursor
            if self.row_count > 0:
                self.move_cursor(row=min(current_cursor_row, self.row_count - 1))
        else:
            # In-place update — just update cell values without clear()
            for i, s in enumerate(sorted_sessions):
                row_key = s.session_id
                row = self._build_row(i + 1, s)
                columns = ["#", "Name", "Status", "Stage", "Cost($)", "Tokens", "Uptime"]
                try:
                    for col, val in zip(columns, row):
                        self.update_cell(row_key, col, val)
                except Exception:
                    pass  # Row may have been removed between check and update

    def set_filter(self, status: SessionStatus | None) -> None:
        """Set status filter. None = show all."""
        self._filter_status = status
        self.update_sessions(self._all_sessions)

    def cycle_filter(self) -> SessionStatus | None:
        """Cycle through filter options: None → RUN → WAIT → DEAD → DONE → None."""
        cycle = [None, SessionStatus.RUN, SessionStatus.WAIT, SessionStatus.DEAD, SessionStatus.DONE]
        try:
            idx = cycle.index(self._filter_status)
        except ValueError:
            idx = -1
        next_filter = cycle[(idx + 1) % len(cycle)]
        self.set_filter(next_filter)
        return next_filter

    def set_sort(self, sort_key: SortKey) -> None:
        """Set sort key."""
        self._sort_key = sort_key
        self.update_sessions(self._all_sessions)

    def cycle_sort(self) -> SortKey:
        """Cycle through sort options: NONE → COST → STATUS → STAGE → NONE."""
        cycle = [SortKey.NONE, SortKey.COST, SortKey.STATUS, SortKey.STAGE]
        try:
            idx = cycle.index(self._sort_key)
        except ValueError:
            idx = -1
        next_sort = cycle[(idx + 1) % len(cycle)]
        self.set_sort(next_sort)
        return next_sort

    def _apply_filter(self, sessions: list[SessionState]) -> list[SessionState]:
        result = sessions
        if self._filter_status is not None:
            result = [s for s in result if s.status == self._filter_status]
        if self._filter_tag is not None:
            result = [s for s in result if self._filter_tag in s.tags]
        return result

    def _apply_sort(self, sessions: list[SessionState]) -> list[SessionState]:
        if self._sort_key == SortKey.COST:
            result = sorted(sessions, key=lambda s: s.cost_usd, reverse=True)
        elif self._sort_key == SortKey.STATUS:
            result = sorted(sessions, key=lambda s: self.STATUS_ORDER.get(s.status, 99))
        elif self._sort_key == SortKey.STAGE:
            result = sorted(sessions, key=lambda s: s.sop_stage or "Z")
        else:
            result = list(sessions)
        # Pinned sessions always first
        pinned = [s for s in result if s.pinned]
        unpinned = [s for s in result if not s.pinned]
        return pinned + unpinned

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        session_id = str(event.row_key.value) if event.row_key else None
        self.post_message(self.SessionSelected(session_id))
