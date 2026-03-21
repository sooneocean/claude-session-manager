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
from csm.core.persistence import (
    save_sessions, load_sessions,
    save_session_logs, load_session_logs, delete_session_logs,
    cleanup_orphan_logs, export_backup, import_backup,
    save_view_state, load_view_state,
)
from csm.models.session import SessionConfig, SessionStatus
from csm.widgets.session_list import SessionList, SortKey
from csm.widgets.detail_panel import DetailPanel
from csm.widgets.stats_panel import StatsPanel
from csm.core.templates import save_template, load_templates, list_template_names
from csm.widgets.modals import (
    NewSessionModal,
    ConfirmStopModal,
    ConfirmDeleteModal,
    CommandInputModal,
    SearchInputModal,
    NoteInputModal,
    TagInputModal,
    RenameModal,
    RunningWarningModal,
    HelpModal,
    WelcomeScreen,
    TemplateSelectModal,
    SaveTemplateModal,
    CommandPaletteModal,
    BatchOperationModal,
    ScheduleCommandModal,
    SessionInfoModal,
    ImportBackupModal,
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
        Binding("m", "rename_session", "Rename"),
        Binding("T", "filter_by_tag", "Tag Filter", show=False),
        Binding("slash", "filter_sessions", "Filter"),
        Binding("s", "sort_sessions", "Sort"),
        Binding("h", "show_help", "Help"),
        Binding("i", "show_stats", "Stats"),
        Binding("p", "spawn_from_template", "Template"),
        Binding("ctrl+t", "save_as_template", "Save Tpl", show=False),
        Binding("ctrl+p", "command_palette", "Palette", show=False),
        Binding("w", "toggle_wrap", "Wrap", show=False),
        Binding("space", "toggle_pause", "Pause", show=False),
        Binding("asterisk", "toggle_pin", "Pin", show=False),
        Binding("v", "toggle_select", "Select", show=False),
        Binding("V", "batch_operation", "Batch Op", show=False),
        Binding("ctrl+e", "export_backup", "Backup", show=False),
        Binding("ctrl+i", "import_backup", "Import", show=False),
        Binding("ctrl+s", "schedule_command", "Schedule", show=False),
        Binding("g", "session_info", "Info", show=False),
        Binding("o", "cycle_color", "Color", show=False),
        Binding("exclamation_mark", "resend_last", "Resend", show=False),
        Binding("F", "toggle_focus", "Focus", show=False),
        Binding("left_square_bracket", "shrink_list", "List-", show=False),
        Binding("right_square_bracket", "grow_list", "List+", show=False),
        *[Binding(str(k), f"jump_to_session({k})", f"Session {k}", show=False) for k in range(1, 10)],
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield SessionList(id="session_list")
            yield DetailPanel(id="detail_panel")
        yield Static("Total: $0.00 | Sessions: 0", id="status_bar")
        yield Footer()

    def on_mount(self) -> None:
        config_path = getattr(self, '_cli_config_path', None)
        if config_path:
            from pathlib import Path
            self._config = load_config(Path(config_path))
        else:
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
        self._restarting: set[str] = set()  # sessions currently being auto-restarted
        self._last_status: dict[str, SessionStatus] = {}  # track status changes for notifications
        self._selected_ids: set[str] = set()  # multi-select set
        # Restore sessions from previous run
        if not getattr(self, '_cli_no_restore', False):
            self._restore_sessions()
        self.set_interval(self._config.refresh_interval, self._refresh_display)
        # Auto-save timer
        if self._config.auto_save_interval > 0:
            self.set_interval(self._config.auto_save_interval, self._auto_save)
        # Restore view state (filter/sort)
        self._restore_view_state()
        # First-run welcome
        self._check_first_run()

    def _restore_view_state(self) -> None:
        """Restore filter/sort from previous session."""
        from csm.models.session import SessionStatus
        filter_val, sort_val = load_view_state()
        session_list = self.query_one("#session_list", SessionList)
        if filter_val:
            try:
                session_list._filter_status = SessionStatus(filter_val)
            except ValueError:
                pass
        try:
            session_list._sort_key = SortKey(sort_val)
        except ValueError:
            pass

    def _save_view_state(self) -> None:
        """Persist current filter/sort settings."""
        session_list = self.query_one("#session_list", SessionList)
        f = session_list._filter_status.value if session_list._filter_status else None
        s = session_list._sort_key.value
        save_view_state(f, s)

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
            # Sessions saved as RUN/STARTING have no backing process after restart
            if state.status in (SessionStatus.RUN, SessionStatus.STARTING):
                state.status = SessionStatus.DEAD
            self._session_manager._sessions[state.session_id] = state
            buf = self._session_manager._buffer_store.create(
                state.session_id, self._config.output_buffer_capacity
            )
            # Restore saved output logs into the ring buffer
            saved_lines = load_session_logs(state.session_id)
            for line in saved_lines:
                buf.append(line)
            self._session_manager._cost_aggregator.update(
                state.session_id, state.tokens_in, state.tokens_out, state.cost_usd
            )
            self._dispatcher.register_session(state.session_id)
        if saved:
            self.notify(f"Restored {len(saved)} sessions")

    def _auto_save(self) -> None:
        """Periodically save sessions and logs for crash recovery."""
        sessions = self._session_manager.get_sessions()
        if not sessions:
            return
        save_sessions(sessions)
        for s in sessions:
            buf = self._session_manager.buffer_store.get(s.session_id)
            if buf is not None and len(buf) > 0:
                save_session_logs(s.session_id, buf.get_lines())
        # Periodic log cleanup (orphan files older than 7 days)
        active_ids = {s.session_id for s in sessions}
        cleanup_orphan_logs(active_ids)

    def _refresh_display(self) -> None:
        """Refresh the session list, status bar, and detail panel (incremental)."""
        try:
            self._do_refresh()
        except Exception:
            pass  # Never let a display refresh crash the app

    def _do_refresh(self) -> None:
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

        # Status change notifications (configurable)
        for s in sessions:
            prev = self._last_status.get(s.session_id)
            if prev is not None and prev != s.status:
                name = s.config.name or os.path.basename(s.config.cwd)
                if s.status == SessionStatus.DEAD and self._config.notify_on_dead:
                    self.notify(f"'{name}' crashed (DEAD)", severity="error")
                elif s.status == SessionStatus.WAIT and prev == SessionStatus.RUN and self._config.notify_on_wait:
                    self.notify(f"'{name}' ready (WAIT)")
                elif s.status == SessionStatus.DONE and self._config.notify_on_done:
                    self.notify(f"'{name}' completed (DONE)")
            self._last_status[s.session_id] = s.status

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

        # Auto-restart dead sessions (with in-progress guard)
        if self._config.auto_restart_dead:
            for s in sessions:
                if s.status == SessionStatus.DEAD and s.session_id not in self._restarting:
                    count = self._restart_counts.get(s.session_id, 0)
                    if count < self._config.auto_restart_max:
                        self._restart_counts[s.session_id] = count + 1
                        self._restarting.add(s.session_id)
                        name = s.config.name or os.path.basename(s.config.cwd)
                        self.notify(f"Auto-restarting '{name}' (attempt {count + 1})")
                        self._trigger_auto_restart(s.session_id)

        # Session limit warning
        if active >= self._session_manager.SESSION_LIMIT:
            status_text += " [bold red]LIMIT REACHED[/bold red]"

        # Pause indicator
        panel = self.query_one("#detail_panel", DetailPanel)
        if panel.is_paused:
            status_text += " [bold yellow]PAUSED[/bold yellow]"

        # Selected session output stats
        if self._selected_session_id:
            sel = self._session_manager.get_session(self._selected_session_id)
            if sel:
                buf = self._session_manager.buffer_store.get(self._selected_session_id)
                line_count = len(buf) if buf else 0
                ago = int((datetime.now() - sel.last_activity).total_seconds())
                if ago < 60:
                    ago_str = f"{ago}s ago"
                elif ago < 3600:
                    ago_str = f"{ago // 60}m ago"
                else:
                    ago_str = f"{ago // 3600}h ago"
                status_text += f" | {line_count} lines | {ago_str}"

        # Multi-select count
        if self._selected_ids:
            status_text += f" | [bold]{len(self._selected_ids)} selected[/bold]"

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
        finally:
            self._restarting.discard(session_id)

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
        cmd = await self.push_screen_wait(
            CommandInputModal(dir_name, history=session.command_history)
        )
        if cmd:
            try:
                await self._dispatcher.enqueue(self._selected_session_id, cmd)
                session.command_history.append(cmd)
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
            sid = self._selected_session_id
            self._dispatcher.cleanup_session(sid)
            await self._session_manager.remove(sid)
            delete_session_logs(sid)
            self._budget_warned.discard(sid)
            self._restart_counts.pop(sid, None)
            self._restarting.discard(sid)
            self._last_status.pop(sid, None)
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

    def action_rename_session(self) -> None:
        """Rename the selected session."""
        self._do_rename_session()

    @work
    async def _do_rename_session(self) -> None:
        if not self._selected_session_id:
            self.notify("No session selected", severity="warning")
            return
        session = self._session_manager.get_session(self._selected_session_id)
        if not session:
            return
        current = session.config.name or os.path.basename(session.config.cwd)
        new_name = await self.push_screen_wait(RenameModal(current))
        if new_name is not None:
            session.config.name = new_name
            self._refresh_display()
            self.notify(f"Renamed to '{new_name}'")

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
        self._save_view_state()

    def action_sort_sessions(self) -> None:
        """Cycle through sort keys."""
        session_list = self.query_one("#session_list", SessionList)
        current = session_list.cycle_sort()
        self.notify(f"Sort: {current.value}")
        self._save_view_state()

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
        failed = 0
        for s in wait_sessions:
            try:
                await self._dispatcher.enqueue(s.session_id, cmd)
                sent += 1
            except Exception:
                failed += 1
        msg = f"Broadcast sent to {sent}/{len(wait_sessions)} sessions"
        if failed:
            msg += f" ({failed} failed)"
        self.notify(msg, severity="warning" if failed else "information")

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
            delete_session_logs(s.session_id)
            self._budget_warned.discard(s.session_id)
            self._restart_counts.pop(s.session_id, None)
            self._restarting.discard(s.session_id)
            self._last_status.pop(s.session_id, None)
        if self._selected_session_id and not self._session_manager.get_session(self._selected_session_id):
            self._selected_session_id = None
            self.query_one("#detail_panel", DetailPanel).show_placeholder()
        self._refresh_display()
        self.notify(f"Cleaned {len(removable)} sessions")

    def action_show_stats(self) -> None:
        """Show dashboard statistics overlay."""
        sessions = self._session_manager.get_sessions()
        self.push_screen(StatsPanel(sessions))

    def action_jump_to_session(self, index: int) -> None:
        """Jump to session by number (1-9)."""
        session_list = self.query_one("#session_list", SessionList)
        if index <= session_list.row_count:
            session_list.move_cursor(row=index - 1)
            # Trigger selection
            try:
                row_key = list(session_list.rows.keys())[index - 1]
                session_id = str(row_key.value)
                self.on_session_list_session_selected(
                    SessionList.SessionSelected(session_id)
                )
            except (IndexError, KeyError):
                pass

    def action_spawn_from_template(self) -> None:
        """Spawn a new session from a saved template."""
        self._do_spawn_from_template()

    @work
    async def _do_spawn_from_template(self) -> None:
        names = list_template_names()
        if not names:
            self.notify("No templates saved. Select a session and press Ctrl+T to save one.", severity="warning")
            return
        selected = await self.push_screen_wait(TemplateSelectModal(names))
        if not selected:
            return
        templates = load_templates()
        tpl = templates.get(selected)
        if not tpl:
            return
        config = SessionConfig(
            cwd=tpl.get("cwd", os.getcwd()),
            model=tpl.get("model"),
            permission_mode=tpl.get("permission_mode", "auto"),
            name=tpl.get("name"),
            max_budget_usd=tpl.get("max_budget_usd"),
        )
        try:
            sid = await self._session_manager.spawn(config)
            self._dispatcher.register_session(sid)
            self._refresh_display()
            self.notify(f"Spawned from template '{selected}'")
        except Exception as e:
            self.notify(str(e), severity="error")

    def action_save_as_template(self) -> None:
        """Save the selected session's config as a reusable template."""
        self._do_save_as_template()

    @work
    async def _do_save_as_template(self) -> None:
        if not self._selected_session_id:
            self.notify("No session selected", severity="warning")
            return
        session = self._session_manager.get_session(self._selected_session_id)
        if not session:
            return
        suggested = session.config.name or os.path.basename(session.config.cwd)
        name = await self.push_screen_wait(SaveTemplateModal(suggested))
        if not name:
            return
        save_template(name, {
            "cwd": session.config.cwd,
            "model": session.config.model,
            "permission_mode": session.config.permission_mode,
            "name": session.config.name,
            "max_budget_usd": session.config.max_budget_usd,
        })
        self.notify(f"Template '{name}' saved")

    def action_toggle_select(self) -> None:
        """Toggle multi-select for the current session."""
        if not self._selected_session_id:
            return
        sid = self._selected_session_id
        if sid in self._selected_ids:
            self._selected_ids.discard(sid)
            self.notify(f"Deselected ({len(self._selected_ids)} selected)")
        else:
            self._selected_ids.add(sid)
            self.notify(f"Selected ({len(self._selected_ids)} selected)")

    def action_batch_operation(self) -> None:
        """Open batch operation modal for multi-selected sessions."""
        self._do_batch_operation()

    @work
    async def _do_batch_operation(self) -> None:
        if not self._selected_ids:
            self.notify("No sessions selected. Press V to select.", severity="warning")
            return
        op = await self.push_screen_wait(BatchOperationModal(len(self._selected_ids)))
        if not op:
            self._selected_ids.clear()
            return
        count = 0
        if op == "stop":
            for sid in list(self._selected_ids):
                session = self._session_manager.get_session(sid)
                if session and session.status not in (SessionStatus.DONE, SessionStatus.DEAD):
                    self._dispatcher.cleanup_session(sid)
                    await self._session_manager.stop(sid)
                    count += 1
            self.notify(f"Stopped {count} sessions")
        elif op == "delete":
            for sid in list(self._selected_ids):
                session = self._session_manager.get_session(sid)
                if session and session.status in (SessionStatus.DONE, SessionStatus.DEAD):
                    self._dispatcher.cleanup_session(sid)
                    await self._session_manager.remove(sid)
                    delete_session_logs(sid)
                    self._budget_warned.discard(sid)
                    self._restart_counts.pop(sid, None)
                    self._last_status.pop(sid, None)
                    count += 1
            self.notify(f"Deleted {count} sessions")
        elif op == "tag":
            tag_result = await self.push_screen_wait(TagInputModal([]))
            if tag_result is not None:
                for sid in self._selected_ids:
                    session = self._session_manager.get_session(sid)
                    if session:
                        session.tags = list(set(session.tags + tag_result))
                        count += 1
                self.notify(f"Tagged {count} sessions")
        self._selected_ids.clear()
        if self._selected_session_id and not self._session_manager.get_session(self._selected_session_id):
            self._selected_session_id = None
            self.query_one("#detail_panel", DetailPanel).show_placeholder()
        self._refresh_display()

    def action_toggle_pin(self) -> None:
        """Toggle pin/unpin for the selected session."""
        if not self._selected_session_id:
            return
        session = self._session_manager.get_session(self._selected_session_id)
        if not session:
            return
        session.pinned = not session.pinned
        self.notify(f"Session {'pinned' if session.pinned else 'unpinned'}")
        self._refresh_display()

    def action_resend_last(self) -> None:
        """Resend the last command to the selected session."""
        self._do_resend_last()

    @work
    async def _do_resend_last(self) -> None:
        if not self._selected_session_id:
            return
        session = self._session_manager.get_session(self._selected_session_id)
        if not session or not session.command_history:
            self.notify("No previous command to resend", severity="warning")
            return
        if session.status == SessionStatus.DEAD:
            self.notify("Session is dead", severity="error")
            return
        last_cmd = session.command_history[-1]
        try:
            await self._dispatcher.enqueue(self._selected_session_id, last_cmd)
            session.command_history.append(last_cmd)
            self.notify(f"Resent: '{last_cmd[:40]}'")
        except (QueueFullError, SessionDeadError) as e:
            self.notify(str(e), severity="error")

    _COLOR_CYCLE = ["", "red", "green", "blue", "yellow", "magenta", "cyan"]

    def action_cycle_color(self) -> None:
        """Cycle through color labels for the selected session."""
        if not self._selected_session_id:
            return
        session = self._session_manager.get_session(self._selected_session_id)
        if not session:
            return
        try:
            idx = self._COLOR_CYCLE.index(session.color)
        except ValueError:
            idx = 0
        session.color = self._COLOR_CYCLE[(idx + 1) % len(self._COLOR_CYCLE)]
        label = session.color or "none"
        self.notify(f"Color: {label}")
        self._refresh_display()

    def action_toggle_pause(self) -> None:
        """Toggle pause/resume output auto-scrolling."""
        panel = self.query_one("#detail_panel", DetailPanel)
        paused = panel.toggle_pause()
        self.notify(f"Output scroll: {'paused' if paused else 'resumed'}")

    def action_toggle_wrap(self) -> None:
        """Toggle word wrap in the detail panel."""
        panel = self.query_one("#detail_panel", DetailPanel)
        state = panel.toggle_word_wrap()
        self.notify(f"Word wrap: {'on' if state else 'off'}")

    def action_command_palette(self) -> None:
        """Open command palette for quick action search."""
        self._do_command_palette()

    @work
    async def _do_command_palette(self) -> None:
        action_id = await self.push_screen_wait(CommandPaletteModal())
        if action_id:
            try:
                await self.run_action(action_id)
            except Exception:
                self.notify(f"Action '{action_id}' failed", severity="error")

    def action_toggle_focus(self) -> None:
        """Toggle focus mode — hide session list, full-screen detail panel."""
        sl = self.query_one("#session_list", SessionList)
        dp = self.query_one("#detail_panel", DetailPanel)
        if sl.display:
            sl.display = False
            dp.styles.width = "100%"
            self.notify("Focus mode ON (Shift+F to exit)")
        else:
            sl.display = True
            pct = getattr(self, '_list_width_pct', 60)
            sl.styles.width = f"{pct}%"
            dp.styles.width = f"{100 - pct}%"
            self.notify("Focus mode OFF")

    def action_session_info(self) -> None:
        """Show detailed session info overlay."""
        if not self._selected_session_id:
            self.notify("No session selected", severity="warning")
            return
        session = self._session_manager.get_session(self._selected_session_id)
        if not session:
            return
        buf = self._session_manager.buffer_store.get(self._selected_session_id)
        line_count = len(buf) if buf else 0
        self.push_screen(SessionInfoModal(session, line_count))

    def action_schedule_command(self) -> None:
        """Schedule a command to be sent after a delay."""
        self._do_schedule_command()

    @work
    async def _do_schedule_command(self) -> None:
        import asyncio
        if not self._selected_session_id:
            self.notify("No session selected", severity="warning")
            return
        session = self._session_manager.get_session(self._selected_session_id)
        if not session:
            return
        name = session.config.name or os.path.basename(session.config.cwd)
        result = await self.push_screen_wait(ScheduleCommandModal(name))
        if not result:
            return
        cmd, delay = result
        sid = self._selected_session_id
        self.notify(f"Scheduled '{cmd}' in {delay}s")

        await asyncio.sleep(delay)
        try:
            await self._dispatcher.enqueue(sid, cmd)
            session = self._session_manager.get_session(sid)
            if session:
                session.command_history.append(cmd)
            self.notify(f"Scheduled command sent: '{cmd}'")
        except Exception as e:
            self.notify(f"Scheduled command failed: {e}", severity="error")

    def action_shrink_list(self) -> None:
        """Shrink the session list panel width."""
        sl = self.query_one("#session_list", SessionList)
        dp = self.query_one("#detail_panel", DetailPanel)
        # Parse current width percentage, decrease by 10
        current = getattr(self, '_list_width_pct', 60)
        new_pct = max(20, current - 10)
        self._list_width_pct = new_pct
        sl.styles.width = f"{new_pct}%"
        dp.styles.width = f"{100 - new_pct}%"

    def action_grow_list(self) -> None:
        """Grow the session list panel width."""
        sl = self.query_one("#session_list", SessionList)
        dp = self.query_one("#detail_panel", DetailPanel)
        current = getattr(self, '_list_width_pct', 60)
        new_pct = min(80, current + 10)
        self._list_width_pct = new_pct
        sl.styles.width = f"{new_pct}%"
        dp.styles.width = f"{100 - new_pct}%"

    def action_export_backup(self) -> None:
        """Export all sessions and logs to a backup file."""
        sessions = self._session_manager.get_sessions()
        if not sessions:
            self.notify("No sessions to export", severity="warning")
            return
        backup_dir = Path.home() / ".csm" / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = backup_dir / f"csm_backup_{timestamp}.json"
        export_backup(sessions, self._session_manager.buffer_store, filepath)
        self.notify(f"Backup saved: {filepath}")

    def action_import_backup(self) -> None:
        """Import sessions from a backup file."""
        self._do_import_backup()

    @work
    async def _do_import_backup(self) -> None:
        backup_dir = Path.home() / ".csm" / "backups"
        if not backup_dir.exists():
            self.notify("No backup directory found", severity="warning")
            return
        files = sorted(
            [f.name for f in backup_dir.glob("csm_backup_*.json")],
            reverse=True,
        )
        selected = await self.push_screen_wait(ImportBackupModal(files))
        if not selected:
            return
        filepath = backup_dir / selected
        try:
            sessions, logs = import_backup(filepath)
        except Exception as e:
            self.notify(f"Import failed: {e}", severity="error")
            return
        imported = 0
        for state in sessions:
            # Skip if session already exists
            if self._session_manager.get_session(state.session_id):
                continue
            self._session_manager._sessions[state.session_id] = state
            buf = self._session_manager._buffer_store.create(
                state.session_id, self._config.output_buffer_capacity
            )
            for line in logs.get(state.session_id, []):
                buf.append(line)
            self._session_manager._cost_aggregator.update(
                state.session_id, state.tokens_in, state.tokens_out, state.cost_usd
            )
            self._dispatcher.register_session(state.session_id)
            imported += 1
        self._refresh_display()
        self.notify(f"Imported {imported} sessions from backup")

    def action_show_help(self) -> None:
        self.push_screen(HelpModal())

    async def action_quit_app(self) -> None:
        # Save sessions before shutdown — mark running sessions as DEAD
        # since they won't have a backing process after restart
        sessions = self._session_manager.get_sessions()
        for s in sessions:
            if s.status in (SessionStatus.RUN, SessionStatus.STARTING):
                s.status = SessionStatus.DEAD
            # Save output buffer logs per session
            buf = self._session_manager.buffer_store.get(s.session_id)
            if buf is not None:
                save_session_logs(s.session_id, buf.get_lines())
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
    import argparse
    from csm import __version__

    parser = argparse.ArgumentParser(
        prog="csm",
        description="Claude Session Manager - TUI for managing multiple Claude Code sessions",
    )
    parser.add_argument("--version", action="version", version=f"csm {__version__}")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to config file (default: ~/.csm/config.json)")
    parser.add_argument("--no-restore", action="store_true",
                        help="Start fresh without restoring saved sessions")
    args = parser.parse_args()

    app = CSMApp()
    app._cli_config_path = args.config
    app._cli_no_restore = args.no_restore
    app.run()


if __name__ == "__main__":
    main()
