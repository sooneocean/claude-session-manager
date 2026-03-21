"""Modal dialogs for CSM. T11"""
import os
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static, Input, Button, Select
from textual.containers import Vertical, Horizontal

from csm.models.session import SessionConfig, SessionState, SessionStatus


def _modal_css(name: str, border_color: str = "$primary", width: int = 60,
               extra: str = "") -> str:
    """Generate consistent modal CSS."""
    return f"""
    {name} {{ align: center middle; }}
    #dialog {{
        width: {width};
        height: auto;
        border: thick {border_color};
        padding: 1 2;
        {extra}
    }}
    """


class NewSessionModal(ModalScreen):
    """Modal for creating a new session.

    Dismisses with a SessionConfig on confirm, or None on cancel.
    """

    CSS = _modal_css("NewSessionModal", "$primary", 65, "max-height: 90%; overflow-y: auto;")

    PERMISSION_MODES = [
        ("auto", "auto"),
        ("default", "default"),
        ("full", "full"),
    ]

    def __init__(self, default_model: str | None = None,
                 default_permission: str = "auto",
                 default_budget: float | None = None) -> None:
        super().__init__()
        self._default_model = default_model or ""
        self._default_permission = default_permission
        self._default_budget = str(default_budget) if default_budget else ""

    def compose(self) -> ComposeResult:
        default_cwd = os.getcwd()
        with Vertical(id="dialog"):
            yield Static("[bold]New Session[/bold]", classes="title")
            yield Static("Working Directory:")
            yield Input(value=default_cwd, placeholder="/path/to/project", id="cwd_input")
            yield Static("Session Name (optional):")
            yield Input(placeholder="my-project", id="name_input")
            yield Static("Resume ID (optional):")
            yield Input(placeholder="session-id", id="resume_input")
            yield Static("Model (optional):")
            yield Input(value=self._default_model, placeholder="sonnet / opus", id="model_input")
            yield Static("Permission Mode:")
            yield Select(self.PERMISSION_MODES, value=self._default_permission, id="permission_select")
            yield Static("Max Budget USD (optional):")
            yield Input(value=self._default_budget, placeholder="e.g. 5.00", id="budget_input")
            with Horizontal():
                yield Button("Create", variant="primary", id="create_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "create_btn":
            cwd = self.query_one("#cwd_input", Input).value.strip()
            name = self.query_one("#name_input", Input).value.strip() or None
            resume = self.query_one("#resume_input", Input).value.strip() or None
            model = self.query_one("#model_input", Input).value.strip() or None
            permission = self.query_one("#permission_select", Select).value
            budget_str = self.query_one("#budget_input", Input).value.strip()
            budget = None
            if budget_str:
                try:
                    budget = float(budget_str)
                except ValueError:
                    self.notify("Invalid budget amount", severity="error")
                    return
            if cwd:
                self.dismiss(SessionConfig(
                    cwd=cwd,
                    name=name,
                    resume_id=resume,
                    model=model,
                    permission_mode=permission,
                    max_budget_usd=budget,
                ))
        else:
            self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)


class ConfirmStopModal(ModalScreen):
    """Confirm stop session dialog.

    Dismisses with True on confirm, False on cancel.
    """

    CSS = _modal_css("ConfirmStopModal", "$error", 50)

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


class ConfirmDeleteModal(ModalScreen):
    """Confirm delete session dialog.

    Dismisses with True on confirm, False on cancel.
    """

    CSS = _modal_css("ConfirmDeleteModal", "$error", 50)

    def __init__(self, session_name: str) -> None:
        super().__init__()
        self._session_name = session_name

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(f"[bold red]Delete[/bold red] session '{self._session_name}'?")
            yield Static("[dim]This will permanently remove the session from the list.[/dim]")
            with Horizontal():
                yield Button("Delete", variant="error", id="delete_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "delete_btn")

    def key_escape(self) -> None:
        self.dismiss(False)


class TagInputModal(ModalScreen):
    """Modal for adding/editing session tags."""

    CSS = _modal_css("TagInputModal", "$accent")

    def __init__(self, current_tags: list[str] | None = None) -> None:
        super().__init__()
        self._current_tags = ", ".join(current_tags) if current_tags else ""

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("[bold]Session Tags[/bold] (comma-separated)")
            yield Input(value=self._current_tags, placeholder="e.g. frontend, urgent, v2", id="tag_input")
            with Horizontal():
                yield Button("Save", variant="primary", id="save_btn")
                yield Button("Clear", variant="warning", id="clear_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save_btn":
            raw = self.query_one("#tag_input", Input).value
            tags = [t.strip() for t in raw.split(",") if t.strip()]
            self.dismiss(tags)
        elif event.button.id == "clear_btn":
            self.dismiss([])
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        tags = [t.strip() for t in event.value.split(",") if t.strip()]
        self.dismiss(tags)

    def key_escape(self) -> None:
        self.dismiss(None)


class NoteInputModal(ModalScreen):
    """Modal for adding/editing session notes."""

    CSS = _modal_css("NoteInputModal", "$accent", 65)

    def __init__(self, current_note: str = "") -> None:
        super().__init__()
        self._current_note = current_note

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("[bold]Session Notes[/bold]")
            yield Input(value=self._current_note, placeholder="Add a note...", id="note_input")
            with Horizontal():
                yield Button("Save", variant="primary", id="save_btn")
                yield Button("Clear", variant="warning", id="clear_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save_btn":
            self.dismiss(self.query_one("#note_input", Input).value.strip())
        elif event.button.id == "clear_btn":
            self.dismiss("")
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())

    def key_escape(self) -> None:
        self.dismiss(None)


class SearchInputModal(ModalScreen):
    """Modal for searching output text."""

    CSS = _modal_css("SearchInputModal", "$accent")

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("Search output:")
            yield Input(placeholder="Enter search term...", id="search_input")
            with Horizontal():
                yield Button("Search", variant="primary", id="search_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "search_btn":
            term = self.query_one("#search_input", Input).value.strip()
            self.dismiss(term or None)
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        term = event.value.strip()
        self.dismiss(term or None)

    def key_escape(self) -> None:
        self.dismiss(None)


class CommandInputModal(ModalScreen):
    """Modal for entering a command to send to a session.

    Supports command history navigation with Up/Down arrow keys.
    Dismisses with the command string, or None on cancel/empty.
    """

    CSS = _modal_css("CommandInputModal", "$accent", 70)

    QUICK_COMMANDS = [
        "/compact",
        "/help",
        "/cost",
        "/status",
        "/clear",
        "/review",
        "/test",
    ]

    def __init__(self, session_name: str, history: list[str] | None = None) -> None:
        super().__init__()
        self._session_name = session_name
        self._history = list(history) if history else []
        self._history_idx = len(self._history)  # Start past end (new input)
        self._draft = ""  # Save current input when browsing history

    def compose(self) -> ComposeResult:
        hint = f" ({len(self._history)} in history)" if self._history else ""
        quick_btns = " ".join(f"[bold]{c}[/bold]" for c in self.QUICK_COMMANDS[:4])
        with Vertical(id="dialog"):
            yield Static(f"Send command to '{self._session_name}':{hint}")
            yield Input(placeholder="Enter your command... (↑↓ history)", id="cmd_input")
            yield Static(f"[dim]Quick: {quick_btns}[/dim]", id="quick_hint")
            with Horizontal(id="quick_bar"):
                for cmd in self.QUICK_COMMANDS:
                    yield Button(cmd, id=f"qcmd_{cmd.strip('/')}")
            with Horizontal():
                yield Button("Send", variant="primary", id="send_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send_btn":
            cmd = self.query_one("#cmd_input", Input).value.strip()
            self.dismiss(cmd or None)
        elif event.button.id == "cancel_btn":
            self.dismiss(None)
        elif event.button.id and event.button.id.startswith("qcmd_"):
            cmd = "/" + event.button.id.removeprefix("qcmd_")
            self.dismiss(cmd)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        cmd = event.value.strip()
        self.dismiss(cmd or None)

    def key_up(self) -> None:
        """Navigate to previous command in history."""
        if not self._history:
            return
        inp = self.query_one("#cmd_input", Input)
        if self._history_idx == len(self._history):
            self._draft = inp.value  # Save current draft
        if self._history_idx > 0:
            self._history_idx -= 1
            inp.value = self._history[self._history_idx]
            inp.cursor_position = len(inp.value)

    def key_down(self) -> None:
        """Navigate to next command in history."""
        if not self._history:
            return
        inp = self.query_one("#cmd_input", Input)
        if self._history_idx < len(self._history):
            self._history_idx += 1
            if self._history_idx == len(self._history):
                inp.value = self._draft  # Restore draft
            else:
                inp.value = self._history[self._history_idx]
            inp.cursor_position = len(inp.value)

    def key_escape(self) -> None:
        self.dismiss(None)


class RenameModal(ModalScreen):
    """Modal for renaming a session."""

    CSS = _modal_css("RenameModal", "$primary")

    def __init__(self, current_name: str) -> None:
        super().__init__()
        self._current_name = current_name

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("[bold]Rename Session[/bold]")
            yield Input(value=self._current_name, placeholder="New name...", id="name_input")
            with Horizontal():
                yield Button("Rename", variant="primary", id="rename_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "rename_btn":
            self.dismiss(self.query_one("#name_input", Input).value.strip() or None)
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

    def key_escape(self) -> None:
        self.dismiss(None)


class RunningWarningModal(ModalScreen):
    """Warning when sending command to a RUN session.

    Dismisses with True to proceed, False to cancel.
    """

    CSS = _modal_css("RunningWarningModal", "$warning", 55)

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


class WelcomeScreen(ModalScreen):
    """First-run welcome screen shown when ~/.csm/ doesn't exist."""

    CSS = _modal_css("WelcomeScreen", "$success", 65, "padding: 2 3;")

    WELCOME_TEXT = """\
[bold green]Welcome to Claude Session Manager![/bold green]

Manage multiple Claude Code sessions from one dashboard.

[bold underline]Quick Start[/bold underline]

  1. Press [bold]N[/bold] to create your first session
  2. Enter a working directory (your project path)
  3. Watch Claude's output stream in real-time

[bold underline]Key Shortcuts[/bold underline]

  [bold]N[/bold]     New session       [bold]Enter[/bold] Send command
  [bold]X[/bold]     Stop session      [bold]R[/bold]     Restart
  [bold]D[/bold]     Delete session    [bold]B[/bold]     Broadcast to all
  [bold]/[/bold]     Filter            [bold]S[/bold]     Sort
  [bold]H[/bold]     Help              [bold]Q[/bold]     Quit (auto-saves)

Press [bold]N[/bold] to get started, or [bold]Esc[/bold] to close.
"""

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self.WELCOME_TEXT)
            with Horizontal():
                yield Button("Create First Session", variant="success", id="start_btn")
                yield Button("Skip", id="skip_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "start_btn")

    def key_escape(self) -> None:
        self.dismiss(False)


class TemplateSelectModal(ModalScreen):
    """Modal for selecting a session template to spawn."""

    CSS = _modal_css("TemplateSelectModal", "$accent", 60)

    def __init__(self, template_names: list[str]) -> None:
        super().__init__()
        self._template_names = template_names

    def compose(self) -> ComposeResult:
        options = [(name, name) for name in self._template_names]
        with Vertical(id="dialog"):
            yield Static("[bold]Spawn from Template[/bold]")
            if options:
                yield Select(options, prompt="Choose template...", id="template_select")
                with Horizontal():
                    yield Button("Spawn", variant="primary", id="spawn_btn")
                    yield Button("Cancel", id="cancel_btn")
            else:
                yield Static("[dim]No templates saved. Use Ctrl+T to save current session as template.[/dim]")
                yield Button("Close", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "spawn_btn":
            sel = self.query_one("#template_select", Select)
            self.dismiss(sel.value if sel.value != Select.BLANK else None)
        else:
            self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)


class SaveTemplateModal(ModalScreen):
    """Modal for saving current session config as a template."""

    CSS = _modal_css("SaveTemplateModal", "$accent")

    def __init__(self, suggested_name: str = "") -> None:
        super().__init__()
        self._suggested_name = suggested_name

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("[bold]Save as Template[/bold]")
            yield Static("Template name:")
            yield Input(value=self._suggested_name, placeholder="my-template", id="name_input")
            with Horizontal():
                yield Button("Save", variant="primary", id="save_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save_btn":
            self.dismiss(self.query_one("#name_input", Input).value.strip() or None)
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

    def key_escape(self) -> None:
        self.dismiss(None)


class CommandPaletteModal(ModalScreen):
    """Quick action search — fuzzy match all available actions."""

    CSS = _modal_css("CommandPaletteModal", "$accent", 55)

    ACTIONS = [
        ("new_session", "N", "New Session"),
        ("send_command", "Enter", "Send Command"),
        ("stop_session", "X", "Stop Session"),
        ("delete_session", "D", "Delete Session"),
        ("restart_session", "R", "Restart Session"),
        ("export_log", "E", "Export Log"),
        ("duplicate_session", "C", "Clone Session"),
        ("broadcast_command", "B", "Broadcast Command"),
        ("filter_sessions", "/", "Filter by Status"),
        ("sort_sessions", "S", "Sort Sessions"),
        ("search_output", "F", "Search Output"),
        ("annotate_session", "A", "Add Note"),
        ("tag_session", "T", "Add Tag"),
        ("rename_session", "M", "Rename Session"),
        ("show_stats", "I", "Dashboard Stats"),
        ("spawn_from_template", "P", "Spawn from Template"),
        ("save_as_template", "Ctrl+T", "Save as Template"),
        ("toggle_pin", "*", "Pin/Unpin Session"),
        ("toggle_select", "V", "Multi-Select"),
        ("batch_operation", "Shift+V", "Batch Operation"),
        ("schedule_command", "Ctrl+S", "Schedule Command"),
        ("toggle_pause", "Space", "Pause/Resume Output"),
        ("toggle_wrap", "W", "Toggle Word Wrap"),
        ("session_info", "G", "Session Info"),
        ("toggle_focus", "Shift+F", "Focus Mode"),
        ("export_backup", "Ctrl+E", "Export Backup"),
        ("import_backup", "Ctrl+I", "Import Backup"),
        ("shrink_list", "[", "Shrink List Panel"),
        ("grow_list", "]", "Grow List Panel"),
        ("stop_all", "Shift+X", "Stop All"),
        ("delete_all_done", "Shift+D", "Delete All Done"),
        ("show_help", "H", "Help"),
        ("quit_app", "Q", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("[bold]Command Palette[/bold]")
            yield Input(placeholder="Type to filter actions...", id="filter_input")
            yield Static(self._render_list(""), id="action_list")

    def _render_list(self, query: str) -> str:
        lines = []
        q = query.lower()
        for action_id, key, label in self.ACTIONS:
            if q and q not in label.lower() and q not in action_id.lower():
                continue
            lines.append(f"  [bold]{key:>8}[/bold]  {label}")
        return "\n".join(lines) if lines else "[dim]No matching actions[/dim]"

    def on_input_changed(self, event: Input.Changed) -> None:
        self.query_one("#action_list", Static).update(self._render_list(event.value))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        q = event.value.lower().strip()
        for action_id, _key, label in self.ACTIONS:
            if q in label.lower() or q in action_id.lower():
                self.dismiss(action_id)
                return
        self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)


class ScheduleCommandModal(ModalScreen):
    """Modal for scheduling a delayed command."""

    CSS = _modal_css("ScheduleCommandModal", "$accent", 60)

    def __init__(self, session_name: str) -> None:
        super().__init__()
        self._session_name = session_name

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(f"[bold]Schedule Command[/bold] for '{self._session_name}'")
            yield Static("Command:")
            yield Input(placeholder="Enter command...", id="cmd_input")
            yield Static("Delay (seconds):")
            yield Input(value="60", placeholder="seconds", id="delay_input")
            with Horizontal():
                yield Button("Schedule", variant="primary", id="schedule_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "schedule_btn":
            cmd = self.query_one("#cmd_input", Input).value.strip()
            delay_str = self.query_one("#delay_input", Input).value.strip()
            if not cmd:
                self.notify("Command required", severity="error")
                return
            try:
                delay = max(1, int(delay_str))
            except ValueError:
                self.notify("Invalid delay", severity="error")
                return
            self.dismiss((cmd, delay))
        else:
            self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)


class BatchOperationModal(ModalScreen):
    """Modal for selecting a batch operation on multiple sessions."""

    CSS = _modal_css("BatchOperationModal", "$warning", 50)

    def __init__(self, count: int) -> None:
        super().__init__()
        self._count = count

    def compose(self) -> ComposeResult:
        ops = [
            ("stop", "Stop All Selected"),
            ("delete", "Delete All Selected"),
            ("tag", "Tag All Selected"),
        ]
        with Vertical(id="dialog"):
            yield Static(f"[bold]Batch Operation[/bold] ({self._count} sessions selected)")
            yield Select([(label, op_id) for op_id, label in ops], prompt="Choose operation...", id="op_select")
            with Horizontal():
                yield Button("Execute", variant="warning", id="exec_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "exec_btn":
            sel = self.query_one("#op_select", Select)
            self.dismiss(sel.value if sel.value != Select.BLANK else None)
        else:
            self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)


class ImportBackupModal(ModalScreen):
    """Modal for importing a backup file."""

    CSS = _modal_css("ImportBackupModal", "$accent", 65)

    def __init__(self, backup_files: list[str]) -> None:
        super().__init__()
        self._backup_files = backup_files

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("[bold]Import Backup[/bold]")
            if self._backup_files:
                options = [(f, f) for f in self._backup_files]
                yield Select(options, prompt="Choose backup...", id="backup_select")
                with Horizontal():
                    yield Button("Import", variant="primary", id="import_btn")
                    yield Button("Cancel", id="cancel_btn")
            else:
                yield Static("[dim]No backup files found in ~/.csm/backups/[/dim]")
                yield Static("[dim]Use Ctrl+E to create a backup first.[/dim]")
                yield Button("Close", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "import_btn":
            sel = self.query_one("#backup_select", Select)
            self.dismiss(sel.value if sel.value != Select.BLANK else None)
        else:
            self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)


class SessionInfoModal(ModalScreen):
    """Detailed session information overlay."""

    CSS = _modal_css("SessionInfoModal", "$primary", 70, "max-height: 85%;")

    def __init__(self, session: SessionState, output_lines: int = 0) -> None:
        super().__init__()
        self._session = session
        self._output_lines = output_lines

    def compose(self) -> ComposeResult:
        s = self._session
        c = s.config
        status_colors = {
            SessionStatus.RUN: "green", SessionStatus.WAIT: "yellow",
            SessionStatus.DEAD: "red", SessionStatus.DONE: "dim",
            SessionStatus.STARTING: "yellow",
        }
        color = status_colors.get(s.status, "white")

        info = [
            f"[bold]Session Info[/bold]",
            "",
            f"[bold]Status:[/bold]  [{color}]{s.status.value}[/{color}]"
            + ("  [bold yellow]PINNED[/bold yellow]" if s.pinned else ""),
            f"[bold]Name:[/bold]    {c.name or '(unnamed)'}",
            f"[bold]CWD:[/bold]     {c.cwd}",
            f"[bold]Model:[/bold]   {c.model or 'default'}",
            f"[bold]Mode:[/bold]    {c.permission_mode}",
            f"[bold]Budget:[/bold]  {'$' + str(c.max_budget_usd) if c.max_budget_usd else 'unlimited'}",
            "",
            f"[bold]Session ID:[/bold]  {s.session_id[:12]}...",
            f"[bold]Claude ID:[/bold]   {s.claude_session_id or 'N/A'}",
            f"[bold]Resume ID:[/bold]   {c.resume_id or 'N/A'}",
            "",
            f"[bold underline]Metrics[/bold underline]",
            f"  Cost:       ${s.cost_usd:.4f}",
            f"  Rate:       ${s.cost_per_hour:.2f}/hr" if s.cost_per_hour > 0 else "  Rate:       N/A",
            f"  Tokens In:  {s.tokens_in:,}",
            f"  Tokens Out: {s.tokens_out:,}",
            f"  Active:     {s.active_duration_str}",
            f"  Output:     {self._output_lines} lines buffered",
            f"  SOP Stage:  {s.sop_stage or 'N/A'}",
        ]

        if s.tags:
            info.extend(["", f"[bold]Tags:[/bold] {', '.join(s.tags)}"])
        if s.notes:
            info.extend(["", f"[bold]Notes:[/bold] {s.notes}"])
        if s.command_history:
            info.extend(["", f"[bold underline]Recent Commands[/bold underline] (last 5)"])
            for cmd in s.command_history[-5:]:
                info.append(f"  > {cmd[:60]}")

        with Vertical(id="dialog"):
            yield Static("\n".join(info))
            yield Button("Close", variant="primary", id="close_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)


class HelpModal(ModalScreen):
    """Help screen showing keyboard shortcuts and usage info."""

    CSS = _modal_css("HelpModal", "$primary", 65, "max-height: 80%;")

    HELP_TEXT = """\
[bold]Claude Session Manager (CSM)[/bold]

[bold underline]Session Management[/bold underline]

  [bold]N[/bold]       New session          [bold]P[/bold]       Spawn from template
  [bold]Enter[/bold]   Send command         [bold]B[/bold]       Broadcast to all WAIT
  [bold]X[/bold]       Stop session         [bold]Shift+X[/bold] Stop all
  [bold]D[/bold]       Delete session       [bold]Shift+D[/bold] Delete all done
  [bold]R[/bold]       Restart session      [bold]C[/bold]       Clone session

[bold underline]Organization[/bold underline]

  [bold]M[/bold]       Rename               [bold]A[/bold]       Add note
  [bold]T[/bold]       Add tag              [bold]Shift+T[/bold] Filter by tag
  [bold]/[/bold]       Filter by status     [bold]S[/bold]       Sort sessions
  [bold]1-9[/bold]     Quick-switch         [bold]I[/bold]       Dashboard stats
  [bold]*[/bold]       Pin/unpin session    [bold]V[/bold]       Multi-select
  [bold]Shift+V[/bold] Batch operation

[bold underline]Output & Tools[/bold underline]

  [bold]F[/bold]       Search output        [bold]E[/bold]       Export to file
  [bold]G[/bold]       Session info         [bold]Shift+F[/bold] Focus mode
  [bold]W[/bold]       Toggle word wrap     [bold]Space[/bold]   Pause/resume scroll
  [bold][ ][/bold]     Resize panels        [bold]Ctrl+S[/bold]  Schedule command
  [bold]Ctrl+T[/bold]  Save as template     [bold]Ctrl+P[/bold]  Command palette
  [bold]Ctrl+E[/bold]  Export backup        [bold]Ctrl+I[/bold]  Import backup
  [bold]H[/bold]       This help            [bold]Q[/bold]       Quit (auto-saves)

[bold underline]Session States[/bold underline]

  [green]RUN[/green]   Claude is processing    [yellow]WAIT[/yellow]  Ready for commands
  [red]DEAD[/red]  Process crashed          [dim]DONE[/dim]  Stopped normally

[bold underline]CLI Arguments[/bold underline]

  csm --version       Show version
  csm --config PATH   Custom config file
  csm --no-restore    Start fresh
"""

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self.HELP_TEXT)
            yield Button("Close", variant="primary", id="close_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)
