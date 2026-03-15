"""SessionList widget - DataTable showing all sessions. T9"""
import os

from textual.app import ComposeResult
from textual.widgets import DataTable
from textual.message import Message

from csm.models.session import SessionState, SessionStatus


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

    def on_mount(self) -> None:
        self.add_columns("#", "Directory", "Stage", "Status", "Cost($)")
        self.cursor_type = "row"

    def update_sessions(self, sessions: list[SessionState]) -> None:
        """Refresh the table with current session data."""
        self.clear()
        for i, s in enumerate(sessions, 1):
            status_text, _color = self.STATUS_DISPLAY.get(
                s.status, ("?", "white")
            )
            stage = s.sop_stage or "--"
            cost = f"{s.cost_usd:.2f}"
            dir_name = os.path.basename(s.config.cwd) or s.config.cwd
            self.add_row(
                str(i), dir_name, stage, status_text, cost,
                key=s.session_id,
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        session_id = str(event.row_key.value) if event.row_key else None
        self.post_message(self.SessionSelected(session_id))
