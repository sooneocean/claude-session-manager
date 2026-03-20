"""Claude Session Manager - Textual App entry point. T12"""
import os
from datetime import datetime
from pathlib import Path

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from textual import work
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static
from textual.containers import Horizontal
from textual.binding import Binding

from csm.core.config import load_config, UserConfig
from csm.core.session_manager import (
    SessionManager,
    DirectoryNotFoundError,
    DuplicateSessionError,
)
from csm.core.command_dispatcher import CommandDispatcher, QueueFullError, SessionDeadError
from csm.core.persistence import save_sessions, load_sessions
from csm.models.session import SessionConfig, SessionStatus
from csm.widgets.session_list import SessionList, SortKey
from csm.widgets.detail_panel import DetailPanel
from csm.widgets.modals import (
    NewSessionModal,
    ConfirmStopModal,
    ConfirmDeleteModal,
    CommandInputModal,
    SearchInputModal,
    NoteInputModal,
    TagInputModal,
    RunningWarningModal,
    HelpModal,
    WelcomeScreen,
)


class CSMApp(App):
    """Claude Session Manager TUI Application."""

    TITLE = "Claude Session Manager"
    CSS_PATH = "styles/app.tcss"

    BINDINGS = [
        Binding("n", "new_session", "New Session"),
        Binding("x", "stop_session", "Stop"),
        Binding("d", "delete_session", "Delete"),
        Binding("r", "restart_session", "Restart"),
        Binding("e", "export_log", "Export"),
        Binding("c", "duplicate_session", "Clone"),
        Binding("enter", "send_command", "Command"),
        Binding("q", "quit_app", "Quit"),
        Binding("b", "broadcast_command", "Broadcast"),
        Binding("X", "stop_all", "Stop All", show=False),
        Binding("D", "delete_all_done", "Delete Done", show=False),
        Binding("f", "search_output", "Search"),
        Binding("a", "annotate_session", "Note"),
        Binding("t", "tag_session", "Tag"),
        Binding("T", "filter_by_tag", "Tag Filter", show=False),
        Binding("slash", "filter_sessions", "Filter"),
        Binding("s", "sort_sessions", "Sort"),
        Binding("h", "show_help", "Help"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield SessionList(id="session_list")
            yield DetailPanel(id="detail_panel")
        yield Static("Total: $0.00 | Sessions: 0", id="status_bar")
        yield Footer()

    def on_mount(self) -> None:
        self._config = load_config()
        self._session_manager = SessionManager(
            session_limit=self._config.session_limit,
            auto_compact_threshold=self._config.auto_compact_threshold,
            buffer_capacity=self._config.output_buffer_capacity,
        )
        self._dispatcher = CommandDispatcher(self._session_manager)
        self._selected_session_id: str | None = None
        self._budget_warned: set[str] = set()  # session_ids already warned
        self._restart_counts: dict[str, int] = {}  # auto-restart counters
        # Restore sessions from previous run
        self._restore_sessions()
        self.set_interval(self._config.refresh_interval, self._refresh_display)
        # First-run welcome
        self._check_first_run()

    def _check_first_run(self) -> None:
        """Show welcome screen if this is the first time running CSM."""
        from pathlib import Path
        csm_dir = Path.home() / ".csm"
        if not csm_dir.exists():
            self._show_welcome()

    def _show_welcome(self) -> None:
        self._do_welcome()

    @work
    async def _do_welcome(self) -> None:
        should_create = await self.push_screen_wait(WelcomeScreen())
        if should_create:
            self.action_new_session()

    def _restore_sessions(self) -> None:
        """Load sessions saved from a previous CSM run."""
        saved = load_sessions()
        for state in saved:
            self._session_manager._sessions[state.session_id] = state
            self._session_manager._buffer_store.create(state.session_id)
            self._session_manager._cost_aggregator.update(
                state.session_id, state.tokens_in, state.tokens_out, state.cost_usd
            )
            self._dispatcher.register_session(state.session_id)
        if saved:
            self.notify(f"Restored {len(saved)} sessions")

    def _refresh_display(self) -> None:
        """Refresh the session list, status bar, and detail panel (incremental)."""
        sessions = self._session_manager.get_sessions()
        session_list = self.query_one("#session_list", SessionList)
        session_list.update_sessions(sessions)

        total = self._session_manager.cost_aggregator.get_total()
        active = sum(
            1
            for s in sessions
            if s.status not in (SessionStatus.DONE, SessionStatus.DEAD)
        )
        status_text = f"Total: ${total.total_cost_usd:.2f} | Sessions: {active}/{len(sessions)}"

        # Filter/Sort indicators (#8)
        filter_label = session_list._filter_status.value if session_list._filter_status else "All"
        sort_label = session_list._sort_key.value if session_list._sort_key != SortKey.NONE else "none"
        status_text += f" | Filter: {filter_label} | Sort: {sort_label}"

        # Resource monitoring (psutil)
        if HAS_PSUTIL:
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
            status_text += f" | CPU: {cpu:.0f}% RAM: {ram:.0f}%"
            if cpu > 90 or ram > 80:
                status_text += " [bold red]HIGH LOAD[/bold red]"

        # Budget alerts — notify once when session reaches 80% of max_budget
        for s in sessions:
            if (
                s.config.max_budget_usd
                and s.session_id not in self._budget_warned
                and s.cost_usd >= s.config.max_budget_usd * 0.8
            ):
                self._budget_warned.add(s.session_id)
                name = s.config.name or os.path.basename(s.config.cwd)
                pct = int(s.cost_usd / s.config.max_budget_usd * 100)
                self.notify(
                    f"Budget alert: '{name}' at {pct}% (${s.cost_usd:.2f}/${s.config.max_budget_usd:.2f})",
                    severity="warning",
                )

        # Auto-restart dead sessions
        if self._config.auto_restart_dead:
            for s in sessions:
                if s.status == SessionStatus.DEAD:
                    count = self._restart_counts.get(s.session_id, 0)
                    if count < self._config.auto_restart_max:
                        self._restart_counts[s.session_id] = count + 1
                        name = s.config.name or os.path.basename(s.config.cwd)
                        self.notify(f"Auto-restarting '{name}' (attempt {count + 1})")
                        self._trigger_auto_restart(s.session_id)

        # Session limit warning
        if active >= self._session_manager.SESSION_LIMIT:
            status_text += " [bold red]LIMIT REACHED[/bold red]"

        self.query_one("#status_bar", Static).update(status_text)

        # Update detail panel header + output
        if self._selected_session_id:
            panel = self.query_one("#detail_panel", DetailPanel)
            session = self._session_manager.get_session(self._selected_session_id)
            panel.update_header(session)
            buf = self._session_manager.buffer_store.get(self._selected_session_id)
            if buf is not None:
                panel.refresh_from_buffer(self._selected_session_id, buf.get_lines())

    @work
    async def _trigger_auto_restart(self, session_id: str) -> None:
        try:
            self._dispatcher.cleanup_session(session_id)
            new_id = await self._session_manager.restart(session_id)
            self._dispatcher.register_session(new_id)
            # Transfer restart count to new session
            old_count = self._restart_counts.pop(session_id, 0)
            self._restart_counts[new_id] = old_count
        except Exception as e:
            self.notify(f"Auto-restart failed: {e}", severity="error")

    def action_new_session(self) -> None:
        self._do_new_session()

    @work
    async def _do_new_session(self) -> None:
        config = await self.push_screen_wait(NewSessionModal(
            default_model=self._config.default_model,
            default_permission=self._config.default_permission_mode,
            default_budget=self._config.default_max_budget_usd,
        ))
        if config:
            try:
                sid = await self._session_manager.spawn(config)
                self._dispatcher.register_session(sid)
                self._refresh_display()
            except (DirectoryNotFoundError, DuplicateSessionError) as e:
                self.notify(str(e), severity="error")

    def action_send_command(self) -> None:
        self._do_send_command()

    @work
    async def _do_send_command(self) -> None:
        if not self._selected_session_id:
            return
        session = self._session_manager.get_session(self._selected_session_id)
        if not session:
            return

        if session.status == SessionStatus.DEAD:
            self.notify("Session is dead. Restart first.", severity="error")
            return

        if session.status == SessionStatus.RUN:
            proceed = await self.push_screen_wait(RunningWarningModal())
            if not proceed:
                return

        dir_name = os.path.basename(session.config.cwd) or session.config.cwd
        cmd = await self.push_screen_wait(CommandInputModal(dir_name))
        if cmd:
            try:
                await self._dispatcher.enqueue(self._selected_session_id, cmd)
                self.notify("Command sent")
            except (QueueFullError, SessionDeadError) as e:
                self.notify(str(e), severity="error")

    def action_stop_session(self) -> None:
        self._do_stop_session()

    @work
    async def _do_stop_session(self) -> None:
        if not self._selected_session_id:
            return
        session = self._session_manager.get_session(self._selected_session_id)
        if not session:
            return
        dir_name = os.path.basename(session.config.cwd) or session.config.cwd
        confirmed = await self.push_screen_wait(ConfirmStopModal(dir_name))
        if confirmed:
            self._dispatcher.cleanup_session(self._selected_session_id)
            await self._session_manager.stop(self._selected_session_id)
            self._refresh_display()

    def action_delete_session(self) -> None:
        """Delete a DONE/DEAD session from the list."""
        self._do_delete_session()

    @work
    async def _do_delete_session(self) -> None:
        if not self._selected_session_id:
            return
        session = self._session_manager.get_session(self._selected_session_id)
        if not session:
            return

        if session.status not in (SessionStatus.DONE, SessionStatus.DEAD):
            self.notify("Only DONE or DEAD sessions can be deleted. Stop first.", severity="warning")
            return

        dir_name = session.config.name or os.path.basename(session.config.cwd) or session.config.cwd
        confirmed = await self.push_screen_wait(ConfirmDeleteModal(dir_name))
        if confirmed:
            self._dispatcher.cleanup_session(self._selected_session_id)
            await self._session_manager.remove(self._selected_session_id)
            self._selected_session_id = None
            self.query_one("#detail_panel", DetailPanel).show_placeholder()
            self._refresh_display()
            self.notify("Session deleted")

    def action_annotate_session(self) -> None:
        """Add or edit notes for the selected session."""
        self._do_annotate_session()

    @work
    async def _do_annotate_session(self) -> None:
        if not self._selected_session_id:
            self.notify("No session selected", severity="warning")
            return
        session = self._session_manager.get_session(self._selected_session_id)
        if not session:
            return
        result = await self.push_screen_wait(NoteInputModal(session.notes))
        if result is not None:
            session.notes = result
            self.notify("Note saved" if result else "Note cleared")

    def action_tag_session(self) -> None:
        """Add or edit tags for the selected session."""
        self._do_tag_session()

    @work
    async def _do_tag_session(self) -> None:
        if not self._selected_session_id:
            self.notify("No session selected", severity="warning")
            return
        session = self._session_manager.get_session(self._selected_session_id)
        if not session:
            return
        result = await self.push_screen_wait(TagInputModal(session.tags))
        if result is not None:
            session.tags = result
            self.notify(f"Tags: {', '.join(result)}" if result else "Tags cleared")

    def action_filter_by_tag(self) -> None:
        """Cycle through tag-based filtering."""
        sessions = self._session_manager.get_sessions()
        all_tags = sorted(set(t for s in sessions for t in s.tags))
        if not all_tags:
            self.notify("No tags found", severity="warning")
            return
        session_list = self.query_one("#session_list", SessionList)
        current = getattr(session_list, '_filter_tag', None)
        if current in all_tags:
            idx = all_tags.index(current)
            next_tag = all_tags[(idx + 1) % len(all_tags)] if idx + 1 < len(all_tags) else None
        else:
            next_tag = all_tags[0]
        session_list._filter_tag = next_tag
        self.notify(f"Tag filter: {next_tag or 'None'}")

    def action_search_output(self) -> None:
        """Search within the selected session's output."""
        self._do_search_output()

    @work
    async def _do_search_output(self) -> None:
        if not self._selected_session_id:
            self.notify("No session selected", severity="warning")
            return
        buf = self._session_manager.buffer_store.get(self._selected_session_id)
        if not buf:
            self.notify("No output to search", severity="warning")
            return
        term = await self.push_screen_wait(SearchInputModal())
        if not term:
            return
        lines = buf.get_lines()
        panel = self.query_one("#detail_panel", DetailPanel)
        matches = panel.search_output(term, lines)
        self.notify(f"Found {matches} matching lines for '{term}'")

    def action_export_log(self) -> None:
        """Export selected session's output to a file."""
        if not self._selected_session_id:
            self.notify("No session selected", severity="warning")
            return
        session = self._session_manager.get_session(self._selected_session_id)
        if not session:
            return
        buf = self._session_manager.buffer_store.get(self._selected_session_id)
        if not buf:
            self.notify("No output to export", severity="warning")
            return

        lines = buf.get_lines()
        if not lines:
            self.notify("Output buffer is empty", severity="warning")
            return

        export_dir = Path.home() / ".csm" / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        name = session.config.name or os.path.basename(session.config.cwd) or "session"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = export_dir / f"{name}_{timestamp}.log"
        filepath.write_text("\n".join(lines), encoding="utf-8")
        self.notify(f"Exported to {filepath}")

    def action_duplicate_session(self) -> None:
        """Clone the selected session's config into a new session."""
        self._do_duplicate_session()

    @work
    async def _do_duplicate_session(self) -> None:
        if not self._selected_session_id:
            self.notify("No session selected", severity="warning")
            return
        session = self._session_manager.get_session(self._selected_session_id)
        if not session:
            return
        # Create new config without resume_id (fresh session, same dir/model/etc)
        new_config = SessionConfig(
            cwd=session.config.cwd,
            model=session.config.model,
            permission_mode=session.config.permission_mode,
            name=f"{session.config.name or os.path.basename(session.config.cwd)}-copy",
            max_budget_usd=session.config.max_budget_usd,
        )
        try:
            sid = await self._session_manager.spawn(new_config)
            self._dispatcher.register_session(sid)
            self._refresh_display()
            self.notify("Session cloned")
        except Exception as e:
            self.notify(str(e), severity="error")

    def action_restart_session(self) -> None:
        self._do_restart_session()

    @work
    async def _do_restart_session(self) -> None:
        if not self._selected_session_id:
            return
        old_id = self._selected_session_id
        self._dispatcher.cleanup_session(old_id)
        try:
            new_id = await self._session_manager.restart(old_id)
            self._dispatcher.register_session(new_id)
            self._selected_session_id = new_id
            self._refresh_display()
        except Exception as e:
            self.notify(str(e), severity="error")

    def action_filter_sessions(self) -> None:
        """Cycle through status filters."""
        session_list = self.query_one("#session_list", SessionList)
        current = session_list.cycle_filter()
        label = current.value if current else "All"
        self.notify(f"Filter: {label}")

    def action_sort_sessions(self) -> None:
        """Cycle through sort keys."""
        session_list = self.query_one("#session_list", SessionList)
        current = session_list.cycle_sort()
        self.notify(f"Sort: {current.value}")

    def action_broadcast_command(self) -> None:
        self._do_broadcast()

    @work
    async def _do_broadcast(self) -> None:
        """Send the same command to all WAIT sessions."""
        wait_sessions = [
            s for s in self._session_manager.get_sessions()
            if s.status == SessionStatus.WAIT
        ]
        if not wait_sessions:
            self.notify("No WAIT sessions to broadcast to", severity="warning")
            return

        cmd = await self.push_screen_wait(
            CommandInputModal(f"{len(wait_sessions)} WAIT sessions")
        )
        if not cmd:
            return

        sent = 0
        for s in wait_sessions:
            try:
                await self._dispatcher.enqueue(s.session_id, cmd)
                sent += 1
            except Exception:
                pass
        self.notify(f"Broadcast sent to {sent}/{len(wait_sessions)} sessions")

    def action_stop_all(self) -> None:
        """Stop all active sessions."""
        self._do_stop_all()

    @work
    async def _do_stop_all(self) -> None:
        active = [
            s for s in self._session_manager.get_sessions()
            if s.status not in (SessionStatus.DONE, SessionStatus.DEAD)
        ]
        if not active:
            self.notify("No active sessions", severity="warning")
            return
        for s in active:
            self._dispatcher.cleanup_session(s.session_id)
            await self._session_manager.stop(s.session_id)
        self._refresh_display()
        self.notify(f"Stopped {len(active)} sessions")

    def action_delete_all_done(self) -> None:
        """Delete all DONE/DEAD sessions."""
        self._do_delete_all_done()

    @work
    async def _do_delete_all_done(self) -> None:
        removable = [
            s for s in self._session_manager.get_sessions()
            if s.status in (SessionStatus.DONE, SessionStatus.DEAD)
        ]
        if not removable:
            self.notify("No DONE/DEAD sessions to clean", severity="warning")
            return
        for s in removable:
            self._dispatcher.cleanup_session(s.session_id)
            await self._session_manager.remove(s.session_id)
        if self._selected_session_id and not self._session_manager.get_session(self._selected_session_id):
            self._selected_session_id = None
            self.query_one("#detail_panel", DetailPanel).show_placeholder()
        self._refresh_display()
        self.notify(f"Cleaned {len(removable)} sessions")

    def action_show_help(self) -> None:
        self.push_screen(HelpModal())

    async def action_quit_app(self) -> None:
        # Save sessions before shutdown
        sessions = self._session_manager.get_sessions()
        save_sessions(sessions)
        await self._dispatcher.shutdown()
        await self._session_manager.shutdown()
        self.exit()

    def on_session_list_session_selected(self, event: SessionList.SessionSelected) -> None:
        self._selected_session_id = event.session_id
        panel = self.query_one("#detail_panel", DetailPanel)
        if event.session_id:
            session = self._session_manager.get_session(event.session_id)
            panel.track_session(event.session_id)
            panel.update_header(session)
            buf = self._session_manager.buffer_store.get(event.session_id)
            if buf is not None:
                panel.show_output(buf.get_lines(100))
            else:
                panel.show_placeholder()
        else:
            panel.show_placeholder()


def main() -> None:
    app = CSMApp()
    app.run()


if __name__ == "__main__":
    main()
