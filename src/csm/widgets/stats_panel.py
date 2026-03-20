"""StatsPanel widget - dashboard statistics overlay."""
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static, Button
from textual.containers import Vertical

from csm.models.session import SessionState, SessionStatus


class StatsPanel(ModalScreen):
    """Dashboard overlay showing aggregate session statistics."""

    CSS = """
    StatsPanel { align: center middle; }
    #dialog {
        width: 60;
        height: auto;
        max-height: 80%;
        border: thick $primary;
        padding: 1 2;
    }
    """

    def __init__(self, sessions: list[SessionState]) -> None:
        super().__init__()
        self._sessions = sessions

    def compose(self) -> ComposeResult:
        stats = self._compute_stats()
        with Vertical(id="dialog"):
            yield Static(stats)
            yield Button("Close", variant="primary", id="close_btn")

    def _compute_stats(self) -> str:
        sessions = self._sessions
        total = len(sessions)
        if total == 0:
            return "[bold]Dashboard Statistics[/bold]\n\nNo sessions yet."

        by_status = {}
        for s in sessions:
            by_status[s.status] = by_status.get(s.status, 0) + 1

        total_cost = sum(s.cost_usd for s in sessions)
        total_tokens_in = sum(s.tokens_in for s in sessions)
        total_tokens_out = sum(s.tokens_out for s in sessions)
        avg_cost = total_cost / total if total else 0

        all_tags = {}
        for s in sessions:
            for t in s.tags:
                all_tags[t] = all_tags.get(t, 0) + 1

        models = {}
        for s in sessions:
            m = s.config.model or "default"
            models[m] = models.get(m, 0) + 1

        lines = [
            "[bold]Dashboard Statistics[/bold]",
            "",
            f"[bold]Sessions:[/bold] {total}",
        ]

        status_colors = {
            SessionStatus.RUN: "green",
            SessionStatus.WAIT: "yellow",
            SessionStatus.DEAD: "red",
            SessionStatus.DONE: "dim",
            SessionStatus.STARTING: "yellow",
        }
        for status, count in sorted(by_status.items(), key=lambda x: x[0].value):
            color = status_colors.get(status, "white")
            lines.append(f"  [{color}]{status.value}[/{color}]: {count}")

        lines.extend([
            "",
            f"[bold]Cost:[/bold] ${total_cost:.2f} total, ${avg_cost:.2f} avg",
            f"[bold]Tokens:[/bold] {total_tokens_in:,} in / {total_tokens_out:,} out",
        ])

        if models:
            lines.append("")
            lines.append("[bold]Models:[/bold]")
            for m, count in sorted(models.items()):
                lines.append(f"  {m}: {count}")

        if all_tags:
            lines.append("")
            lines.append("[bold]Tags:[/bold]")
            for tag, count in sorted(all_tags.items(), key=lambda x: -x[1]):
                lines.append(f"  {tag}: {count}")

        return "\n".join(lines)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)
