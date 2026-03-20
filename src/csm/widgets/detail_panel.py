"""DetailPanel widget - shows recent output of selected session. T10 + v3 streaming"""
from textual.widgets import RichLog, Static
from textual.containers import Vertical

from csm.models.session import SessionState, SessionStatus


class SessionHeader(Static):
    """Header bar showing selected session info."""

    STATUS_STYLE = {
        SessionStatus.STARTING: "yellow",
        SessionStatus.RUN: "bold green",
        SessionStatus.WAIT: "bold yellow",
        SessionStatus.DONE: "dim",
        SessionStatus.DEAD: "bold red",
    }

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)

    def update_session(self, session: SessionState | None) -> None:
        if session is None:
            self.update("[dim]No session selected[/dim]")
            return
        name = session.config.name or session.config.cwd
        status = session.status.value
        style = self.STATUS_STYLE.get(session.status, "white")
        tokens = f"{session.tokens_in + session.tokens_out:,}"
        cost = f"${session.cost_usd:.2f}"
        model = session.config.model or "default"
        text = f" [{style}]{status}[/{style}]  {name}  |  {model}  |  {tokens} tokens  |  {cost}"
        if session.notes:
            text += f"  | [italic]{session.notes}[/italic]"
        self.update(text)


class DetailPanel(Vertical):
    """Shows session header + recent output of the selected session's ring buffer."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._tracking_session_id: str | None = None
        self._last_line_count: int = 0

    def compose(self):
        yield SessionHeader(id="session_header")
        yield RichLog(id="output_log")

    def on_mount(self) -> None:
        self.show_placeholder()

    @property
    def _log(self) -> RichLog:
        return self.query_one("#output_log", RichLog)

    @property
    def _header(self) -> SessionHeader:
        return self.query_one("#session_header", SessionHeader)

    def update_header(self, session: SessionState | None) -> None:
        """Update the session info header."""
        self._header.update_session(session)

    def show_output(self, lines: list[str]) -> None:
        """Display lines from a session's ring buffer (batch mode)."""
        self._log.clear()
        for line in lines:
            self._log.write(line)
        self._last_line_count = len(lines)

    def show_placeholder(self) -> None:
        """Display placeholder text when no session is selected."""
        self._tracking_session_id = None
        self._last_line_count = 0
        self._header.update_session(None)
        self._log.clear()
        self._log.write("[dim]Select a session to view output[/dim]")

    def track_session(self, session_id: str | None) -> None:
        """Set which session this panel is tracking for incremental updates."""
        self._tracking_session_id = session_id
        self._last_line_count = 0

    def search_output(self, term: str, lines: list[str]) -> None:
        """Search and highlight matching lines in the output."""
        self._log.clear()
        matches = 0
        for line in lines:
            if term.lower() in line.lower():
                self._log.write(f"[bold yellow]>>> {line}[/bold yellow]")
                matches += 1
            else:
                self._log.write(line)
        self._last_line_count = len(lines)
        return matches

    def refresh_from_buffer(self, session_id: str, lines: list[str]) -> None:
        """Incrementally append new lines from a ring buffer."""
        if session_id != self._tracking_session_id:
            return

        new_count = len(lines)
        if new_count > self._last_line_count:
            for line in lines[self._last_line_count:]:
                self._log.write(line)
            self._last_line_count = new_count
