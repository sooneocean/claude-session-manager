"""DetailPanel widget - shows recent output of selected session. T10 + v3 streaming"""
from textual.widgets import RichLog


class DetailPanel(RichLog):
    """Shows recent output of the selected session's ring buffer.

    Supports both batch display (show_output) and real-time streaming
    (append_line) for live session output.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._tracking_session_id: str | None = None
        self._last_line_count: int = 0

    def on_mount(self) -> None:
        self.show_placeholder()

    def show_output(self, lines: list[str]) -> None:
        """Display lines from a session's ring buffer (batch mode)."""
        self.clear()
        for line in lines:
            self.write(line)
        self._last_line_count = len(lines)

    def show_placeholder(self) -> None:
        """Display placeholder text when no session is selected."""
        self._tracking_session_id = None
        self._last_line_count = 0
        self.clear()
        self.write("[dim]Select a session to view output[/dim]")

    def track_session(self, session_id: str | None) -> None:
        """Set which session this panel is tracking for incremental updates."""
        self._tracking_session_id = session_id
        self._last_line_count = 0

    def refresh_from_buffer(self, session_id: str, lines: list[str]) -> None:
        """Incrementally append new lines from a ring buffer.

        Only writes lines that haven't been displayed yet, avoiding
        full clear+redraw on every refresh cycle.
        """
        if session_id != self._tracking_session_id:
            return

        new_count = len(lines)
        if new_count > self._last_line_count:
            # Append only the new lines
            for line in lines[self._last_line_count:]:
                self.write(line)
            self._last_line_count = new_count
