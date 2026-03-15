"""DetailPanel widget - shows recent output of selected session. T10"""
from textual.widgets import RichLog


class DetailPanel(RichLog):
    """Shows recent output of the selected session's ring buffer."""

    def on_mount(self) -> None:
        self.show_placeholder()

    def show_output(self, lines: list[str]) -> None:
        """Display lines from a session's ring buffer (last 100 lines)."""
        self.clear()
        for line in lines[-100:]:
            self.write(line)

    def show_placeholder(self) -> None:
        """Display placeholder text when no session is selected."""
        self.clear()
        self.write("[dim]Select a session to view output[/dim]")
