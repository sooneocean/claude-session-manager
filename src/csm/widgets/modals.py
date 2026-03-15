"""Modal dialogs for CSM. T11"""
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static, Input, Button
from textual.containers import Vertical, Horizontal

from csm.models.session import SessionConfig


class NewSessionModal(ModalScreen):
    """Modal for creating a new session.

    Dismisses with a SessionConfig on confirm, or None on cancel.
    """

    CSS = """
    NewSessionModal { align: center middle; }
    #dialog {
        width: 60;
        height: auto;
        border: thick $primary;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("New Session", classes="title")
            yield Static("Working Directory:")
            yield Input(placeholder="/path/to/project", id="cwd_input")
            yield Static("Session Name (optional):")
            yield Input(placeholder="my-project", id="name_input")
            yield Static("Resume ID (optional):")
            yield Input(placeholder="session-id", id="resume_input")
            yield Static("Model (optional):")
            yield Input(placeholder="sonnet / opus", id="model_input")
            with Horizontal():
                yield Button("Create", variant="primary", id="create_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "create_btn":
            cwd = self.query_one("#cwd_input", Input).value.strip()
            name = self.query_one("#name_input", Input).value.strip() or None
            resume = self.query_one("#resume_input", Input).value.strip() or None
            model = self.query_one("#model_input", Input).value.strip() or None
            if cwd:
                self.dismiss(SessionConfig(cwd=cwd, name=name, resume_id=resume, model=model))
            # If cwd is empty, stay open (do nothing)
        else:
            self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)


class ConfirmStopModal(ModalScreen):
    """Confirm stop session dialog.

    Dismisses with True on confirm, False on cancel.
    """

    CSS = """
    ConfirmStopModal { align: center middle; }
    #dialog {
        width: 50;
        height: auto;
        border: thick $error;
        padding: 1 2;
    }
    """

    def __init__(self, session_name: str) -> None:
        super().__init__()
        self._session_name = session_name

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(f"Stop session '{self._session_name}'?")
            with Horizontal():
                yield Button("Stop", variant="error", id="stop_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "stop_btn")

    def key_escape(self) -> None:
        self.dismiss(False)


class CommandInputModal(ModalScreen):
    """Modal for entering a command to send to a session.

    Dismisses with the command string, or None on cancel/empty.
    """

    CSS = """
    CommandInputModal { align: center middle; }
    #dialog {
        width: 70;
        height: auto;
        border: thick $accent;
        padding: 1 2;
    }
    """

    def __init__(self, session_name: str) -> None:
        super().__init__()
        self._session_name = session_name

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(f"Send command to '{self._session_name}':")
            yield Input(placeholder="Enter your command...", id="cmd_input")
            with Horizontal():
                yield Button("Send", variant="primary", id="send_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send_btn":
            cmd = self.query_one("#cmd_input", Input).value.strip()
            self.dismiss(cmd or None)
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        cmd = event.value.strip()
        self.dismiss(cmd or None)

    def key_escape(self) -> None:
        self.dismiss(None)


class RunningWarningModal(ModalScreen):
    """Warning when sending command to a RUN session.

    Dismisses with True to proceed, False to cancel.
    """

    CSS = """
    RunningWarningModal { align: center middle; }
    #dialog {
        width: 55;
        height: auto;
        border: thick $warning;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("[bold yellow]Warning[/bold yellow]")
            yield Static("This session is currently executing.")
            yield Static("Sending a command may interrupt its work.")
            with Horizontal():
                yield Button("Proceed", variant="warning", id="proceed_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "proceed_btn")

    def key_escape(self) -> None:
        self.dismiss(False)


class HelpModal(ModalScreen):
    """Help screen showing keyboard shortcuts and usage info."""

    CSS = """
    HelpModal { align: center middle; }
    #dialog {
        width: 65;
        height: auto;
        border: thick $primary;
        padding: 1 2;
        max-height: 80%;
    }
    """

    HELP_TEXT = """\
[bold]Claude Session Manager (CSM)[/bold]

[bold underline]Keyboard Shortcuts[/bold underline]

  [bold]N[/bold]     New session (specify dir, name, model)
  [bold]Enter[/bold] Send command to selected session
  [bold]X[/bold]     Stop selected session
  [bold]R[/bold]     Restart selected session
  [bold]B[/bold]     Broadcast command to all WAIT sessions
  [bold]/[/bold]     Filter by status (cycle: All/RUN/WAIT/DEAD/DONE)
  [bold]S[/bold]     Sort (cycle: None/Cost/Status/Stage)
  [bold]H[/bold]     This help screen
  [bold]Q[/bold]     Quit (sessions are saved)

[bold underline]Session States[/bold underline]

  [green]RUN[/green]   Claude is processing a command
  [yellow]WAIT[/yellow]  Ready for your next command
  [red]DEAD[/red]  Process crashed (press R to restart)
  [dim]DONE[/dim]  Session stopped normally

[bold underline]Architecture[/bold underline]

  Each interaction spawns: claude -p --resume --output-format stream-json
  Output is streamed line-by-line to the detail panel in real-time.
  Sessions persist to ~/.csm/sessions.json on quit.
"""

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self.HELP_TEXT)
            yield Button("Close", variant="primary", id="close_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)
