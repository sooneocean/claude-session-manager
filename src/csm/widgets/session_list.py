"""SessionList widget - DataTable showing all sessions. T9 + v2 refactor"""
import os
from enum import Enum

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
        self._sort_key: SortKey = SortKey.NONE
        self._all_sessions: list[SessionState] = []

    def on_mount(self) -> None:
        self.add_columns("#", "Directory", "Stage", "Status", "Cost($)")
        self.cursor_type = "row"

    def update_sessions(self, sessions: list[SessionState]) -> None:
        """Refresh the table with current session data using differential update."""
        self._all_sessions = sessions
        filtered = self._apply_filter(sessions)
        sorted_sessions = self._apply_sort(filtered)

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
                status_text, _color = self.STATUS_DISPLAY.get(s.status, ("?", "white"))
                stage = s.sop_stage or "--"
                cost = f"{s.cost_usd:.2f}"
                dir_name = os.path.basename(s.config.cwd) or s.config.cwd
                self.add_row(str(i), dir_name, stage, status_text, cost, key=s.session_id)
            # Restore cursor
            if self.row_count > 0:
                self.move_cursor(row=min(current_cursor_row, self.row_count - 1))
        else:
            # In-place update — just update cell values without clear()
            for i, s in enumerate(sorted_sessions):
                status_text, _color = self.STATUS_DISPLAY.get(s.status, ("?", "white"))
                stage = s.sop_stage or "--"
                cost = f"{s.cost_usd:.2f}"
                dir_name = os.path.basename(s.config.cwd) or s.config.cwd
                row_key = s.session_id
                try:
                    self.update_cell(row_key, "#", str(i + 1))
                    self.update_cell(row_key, "Directory", dir_name)
                    self.update_cell(row_key, "Stage", stage)
                    self.update_cell(row_key, "Status", status_text)
                    self.update_cell(row_key, "Cost($)", cost)
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
        if self._filter_status is None:
            return sessions
        return [s for s in sessions if s.status == self._filter_status]

    def _apply_sort(self, sessions: list[SessionState]) -> list[SessionState]:
        if self._sort_key == SortKey.COST:
            return sorted(sessions, key=lambda s: s.cost_usd, reverse=True)
        elif self._sort_key == SortKey.STATUS:
            return sorted(sessions, key=lambda s: self.STATUS_ORDER.get(s.status, 99))
        elif self._sort_key == SortKey.STAGE:
            return sorted(sessions, key=lambda s: s.sop_stage or "Z")
        return sessions

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        session_id = str(event.row_key.value) if event.row_key else None
        self.post_message(self.SessionSelected(session_id))
