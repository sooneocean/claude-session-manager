"""Claude Session Manager - Textual App entry point. T12"""
import os

from textual import work
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static
from textual.containers import Horizontal
from textual.binding import Binding

from csm.core.session_manager import (
    SessionManager,
    DirectoryNotFoundError,
    DuplicateSessionError,
)
from csm.core.command_dispatcher import CommandDispatcher, QueueFullError, SessionDeadError
from csm.core.persistence import save_sessions, load_sessions
from csm.models.session import SessionStatus
from csm.widgets.session_list import SessionList
from csm.widgets.detail_panel import DetailPanel
from csm.widgets.modals import (
    NewSessionModal,
    ConfirmStopModal,
    CommandInputModal,
    RunningWarningModal,
)


class CSMApp(App):
    """Claude Session Manager TUI Application."""

    TITLE = "Claude Session Manager"
    CSS_PATH = "styles/app.tcss"

    BINDINGS = [
        Binding("n", "new_session", "New Session"),
        Binding("x", "stop_session", "Stop"),
        Binding("r", "restart_session", "Restart"),
        Binding("enter", "send_command", "Command"),
        Binding("q", "quit_app", "Quit"),
        Binding("slash", "filter_sessions", "Filter"),
        Binding("s", "sort_sessions", "Sort"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield SessionList(id="session_list")
            yield DetailPanel(id="detail_panel")
        yield Static("Total: $0.00 | Sessions: 0", id="status_bar")
        yield Footer()

    def on_mount(self) -> None:
        self._session_manager = SessionManager()
        self._dispatcher = CommandDispatcher(self._session_manager)
        self._selected_session_id: str | None = None
        # Restore sessions from previous run
        self._restore_sessions()
        self.set_interval(1.0, self._refresh_display)

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
        """Refresh the session list and status bar."""
        sessions = self._session_manager.get_sessions()
        self.query_one("#session_list", SessionList).update_sessions(sessions)

        total = self._session_manager.cost_aggregator.get_total()
        active = sum(
            1
            for s in sessions
            if s.status not in (SessionStatus.DONE, SessionStatus.DEAD)
        )
        self.query_one("#status_bar", Static).update(
            f"Total: ${total.total_cost_usd:.2f} | Sessions: {active}/{len(sessions)}"
        )

    def action_new_session(self) -> None:
        self._do_new_session()

    @work
    async def _do_new_session(self) -> None:
        config = await self.push_screen_wait(NewSessionModal())
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
        from csm.widgets.session_list import SortKey
        session_list = self.query_one("#session_list", SessionList)
        current = session_list.cycle_sort()
        self.notify(f"Sort: {current.value}")

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
