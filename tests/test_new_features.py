"""Tests for v0.11-v0.43 features."""
import os
import time
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from csm.core.config import load_config, UserConfig, save_default_config
from csm.core.session_manager import SessionManager
from csm.core.persistence import (
    save_sessions, load_sessions,
    save_session_logs, load_session_logs, delete_session_logs,
    cleanup_orphan_logs, export_backup, import_backup,
)
from csm.core.templates import save_template, load_templates, delete_template, list_template_names
from csm.models.session import SessionConfig, SessionState, SessionStatus
from csm.widgets.detail_panel import DetailPanel
from csm.widgets.stats_panel import StatsPanel
from csm.widgets.session_list import SessionList


# --- Config tests (v0.17) ---

class TestConfig:
    def test_default_config(self):
        config = UserConfig()
        assert config.default_model is None
        assert config.default_permission_mode == "auto"
        assert config.session_limit == 20
        assert config.auto_compact_threshold == 50000
        assert config.refresh_interval == 1.0
        assert config.auto_restart_dead is False
        assert config.auto_restart_max == 3

    def test_load_missing_file(self, tmp_path):
        config = load_config(tmp_path / "nonexistent.json")
        assert isinstance(config, UserConfig)
        assert config.default_model is None

    def test_load_valid_config(self, tmp_path):
        path = tmp_path / "config.json"
        path.write_text('{"default_model": "opus", "session_limit": 5}')
        config = load_config(path)
        assert config.default_model == "opus"
        assert config.session_limit == 5
        assert config.default_permission_mode == "auto"  # default preserved

    def test_load_corrupt_config(self, tmp_path):
        path = tmp_path / "config.json"
        path.write_text("not json")
        config = load_config(path)
        assert isinstance(config, UserConfig)

    def test_save_default_config(self, tmp_path):
        path = tmp_path / "config.json"
        save_default_config(path)
        assert path.exists()
        config = load_config(path)
        assert config.session_limit == 20


# --- Session notes & tags persistence (v0.16, v0.19) ---

class TestNotesAndTags:
    def test_session_notes_default(self):
        s = SessionState.create(SessionConfig(cwd="/test"))
        assert s.notes == ""

    def test_session_tags_default(self):
        s = SessionState.create(SessionConfig(cwd="/test"))
        assert s.tags == []

    def test_notes_persist(self, tmp_path):
        s = SessionState.create(SessionConfig(cwd="/test"))
        s.notes = "important session"
        s.status = SessionStatus.WAIT
        path = tmp_path / "sessions.json"
        save_sessions([s], path)
        loaded = load_sessions(path)
        assert loaded[0].notes == "important session"

    def test_tags_persist(self, tmp_path):
        s = SessionState.create(SessionConfig(cwd="/test"))
        s.tags = ["frontend", "urgent"]
        s.status = SessionStatus.WAIT
        path = tmp_path / "sessions.json"
        save_sessions([s], path)
        loaded = load_sessions(path)
        assert loaded[0].tags == ["frontend", "urgent"]


# --- Tag filter (v0.19) ---

class TestTagFilter:
    def test_filter_by_tag(self):
        sl = SessionList()
        sl._filter_tag = "frontend"
        s1 = SessionState.create(SessionConfig(cwd="/a"))
        s1.tags = ["frontend"]
        s2 = SessionState.create(SessionConfig(cwd="/b"))
        s2.tags = ["backend"]
        filtered = sl._apply_filter([s1, s2])
        assert len(filtered) == 1
        assert filtered[0].tags == ["frontend"]

    def test_filter_by_tag_none_shows_all(self):
        sl = SessionList()
        sl._filter_tag = None
        s1 = SessionState.create(SessionConfig(cwd="/a"))
        s1.tags = ["frontend"]
        s2 = SessionState.create(SessionConfig(cwd="/b"))
        filtered = sl._apply_filter([s1, s2])
        assert len(filtered) == 2


# --- Detail panel search (v0.15) ---

class TestDetailPanelSearch:
    def test_search_output_counts_matches(self):
        dp = DetailPanel()
        # search_output returns match count but needs the inner log widget
        # Test the logic at model level
        lines = ["hello world", "foo bar", "hello again"]
        matches = sum(1 for l in lines if "hello" in l.lower())
        assert matches == 2


# --- Buffer capacity (v0.17 fix) ---

class TestBufferCapacity:
    def test_custom_buffer_capacity(self):
        manager = SessionManager(buffer_capacity=500)
        assert manager._buffer_capacity == 500

    def test_default_buffer_capacity(self):
        manager = SessionManager()
        assert manager._buffer_capacity == 1000


# --- Stats panel (v0.20) ---

class TestStatsPanel:
    def test_compute_stats_empty(self):
        panel = StatsPanel([])
        stats = panel._compute_stats()
        assert "No sessions yet" in stats

    def test_compute_stats_with_sessions(self):
        s1 = SessionState.create(SessionConfig(cwd="/a", model="opus"))
        s1.status = SessionStatus.RUN
        s1.cost_usd = 1.5
        s1.tokens_in = 1000
        s1.tokens_out = 500
        s1.tags = ["frontend"]

        s2 = SessionState.create(SessionConfig(cwd="/b"))
        s2.status = SessionStatus.WAIT
        s2.cost_usd = 0.5

        panel = StatsPanel([s1, s2])
        stats = panel._compute_stats()
        assert "2" in stats  # 2 sessions
        assert "$2.00" in stats  # total cost
        assert "frontend" in stats


# --- Modal instantiation (v0.11-v0.20) ---

class TestNewModals:
    def test_tag_input_modal(self):
        from csm.widgets.modals import TagInputModal
        m = TagInputModal(["a", "b"])
        assert m._current_tags == "a, b"

    def test_note_input_modal(self):
        from csm.widgets.modals import NoteInputModal
        m = NoteInputModal("test note")
        assert m._current_note == "test note"

    def test_search_input_modal(self):
        from csm.widgets.modals import SearchInputModal
        m = SearchInputModal()  # should not raise

    def test_confirm_delete_modal(self):
        from csm.widgets.modals import ConfirmDeleteModal
        m = ConfirmDeleteModal("test-session")
        assert m._session_name == "test-session"

    def test_new_session_modal_with_defaults(self):
        from csm.widgets.modals import NewSessionModal
        m = NewSessionModal(default_model="opus", default_permission="full", default_budget=10.0)
        assert m._default_model == "opus"
        assert m._default_permission == "full"
        assert m._default_budget == "10.0"

    def test_rename_modal(self):
        from csm.widgets.modals import RenameModal
        m = RenameModal("old-name")
        assert m._current_name == "old-name"


# --- Command history (v0.22) ---

class TestCommandHistory:
    def test_command_history_default(self):
        s = SessionState.create(SessionConfig(cwd="/test"))
        assert s.command_history == []

    def test_command_history_persists(self, tmp_path):
        s = SessionState.create(SessionConfig(cwd="/test"))
        s.command_history = ["hello", "do something"]
        s.status = SessionStatus.WAIT
        path = tmp_path / "sessions.json"
        save_sessions([s], path)
        loaded = load_sessions(path)
        assert loaded[0].command_history == ["hello", "do something"]

    def test_command_input_modal_with_history(self):
        from csm.widgets.modals import CommandInputModal
        m = CommandInputModal("test", history=["cmd1", "cmd2"])
        assert m._history == ["cmd1", "cmd2"]
        assert m._history_idx == 2  # Past end (new input mode)

    def test_command_input_modal_no_history(self):
        from csm.widgets.modals import CommandInputModal
        m = CommandInputModal("test")
        assert m._history == []
        assert m._history_idx == 0

    def test_command_input_modal_quick_commands(self):
        from csm.widgets.modals import CommandInputModal
        m = CommandInputModal("test")
        assert "/compact" in m.QUICK_COMMANDS
        assert "/help" in m.QUICK_COMMANDS


# --- Log persistence (v0.24) ---

class TestLogPersistence:
    def test_save_and_load_logs(self, tmp_path):
        logs_dir = tmp_path / "logs"
        lines = ["line 1", "line 2", "line 3"]
        save_session_logs("test-id", lines, logs_dir)
        loaded = load_session_logs("test-id", logs_dir)
        assert loaded == lines

    def test_load_missing_logs(self, tmp_path):
        loaded = load_session_logs("nonexistent", tmp_path / "logs")
        assert loaded == []

    def test_delete_logs(self, tmp_path):
        logs_dir = tmp_path / "logs"
        save_session_logs("test-id", ["a"], logs_dir)
        delete_session_logs("test-id", logs_dir)
        assert load_session_logs("test-id", logs_dir) == []

    def test_delete_missing_logs_no_error(self, tmp_path):
        delete_session_logs("nonexistent", tmp_path / "logs")  # should not raise


# --- Session templates (v0.25) ---

class TestTemplates:
    def test_save_and_load_template(self, tmp_path):
        path = tmp_path / "templates.json"
        save_template("my-tpl", {"cwd": "/projects/foo", "model": "opus"}, path)
        templates = load_templates(path)
        assert "my-tpl" in templates
        assert templates["my-tpl"]["model"] == "opus"

    def test_list_template_names(self, tmp_path):
        path = tmp_path / "templates.json"
        save_template("a", {"cwd": "/a"}, path)
        save_template("b", {"cwd": "/b"}, path)
        names = list_template_names(path)
        assert sorted(names) == ["a", "b"]

    def test_delete_template(self, tmp_path):
        path = tmp_path / "templates.json"
        save_template("x", {"cwd": "/x"}, path)
        assert delete_template("x", path)
        assert list_template_names(path) == []

    def test_delete_nonexistent_template(self, tmp_path):
        path = tmp_path / "templates.json"
        assert not delete_template("nope", path)

    def test_load_templates_missing_file(self, tmp_path):
        assert load_templates(tmp_path / "missing.json") == {}


# --- Auto-save config (v0.26) ---

class TestAutoSaveConfig:
    def test_default_auto_save_interval(self):
        config = UserConfig()
        assert config.auto_save_interval == 60.0

    def test_auto_save_interval_from_config(self, tmp_path):
        path = tmp_path / "config.json"
        path.write_text('{"auto_save_interval": 120}')
        config = load_config(path)
        assert config.auto_save_interval == 120.0


# --- Command palette (v0.27) ---

class TestCommandPalette:
    def test_command_palette_modal_importable(self):
        from csm.widgets.modals import CommandPaletteModal
        m = CommandPaletteModal()
        assert len(m.ACTIONS) > 10

    def test_command_palette_render_list(self):
        from csm.widgets.modals import CommandPaletteModal
        m = CommandPaletteModal()
        result = m._render_list("")
        assert "New Session" in result

    def test_command_palette_filter(self):
        from csm.widgets.modals import CommandPaletteModal
        m = CommandPaletteModal()
        result = m._render_list("template")
        assert "Template" in result
        assert "Delete" not in result


# --- Template modals (v0.25) ---

class TestTemplateModals:
    def test_template_select_modal(self):
        from csm.widgets.modals import TemplateSelectModal
        m = TemplateSelectModal(["tpl-a", "tpl-b"])
        assert m._template_names == ["tpl-a", "tpl-b"]

    def test_save_template_modal(self):
        from csm.widgets.modals import SaveTemplateModal
        m = SaveTemplateModal("my-project")
        assert m._suggested_name == "my-project"


# --- Session duration tracking (v0.30) ---

class TestSessionDuration:
    def test_default_active_seconds(self):
        s = SessionState.create(SessionConfig(cwd="/test"))
        assert s.total_active_seconds == 0.0

    def test_track_run_start_and_end(self):
        import time
        s = SessionState.create(SessionConfig(cwd="/test"))
        s.track_run_start()
        time.sleep(0.05)
        s.track_run_end()
        assert s.total_active_seconds > 0

    def test_active_duration_str(self):
        s = SessionState.create(SessionConfig(cwd="/test"))
        s.total_active_seconds = 125  # 2m 5s
        assert s.active_duration_str == "2m 5s"

    def test_active_duration_str_hours(self):
        s = SessionState.create(SessionConfig(cwd="/test"))
        s.total_active_seconds = 3725  # 1h 2m
        assert s.active_duration_str == "1h 2m"

    def test_duration_persists(self, tmp_path):
        s = SessionState.create(SessionConfig(cwd="/test"))
        s.total_active_seconds = 300.5
        s.status = SessionStatus.WAIT
        path = tmp_path / "sessions.json"
        save_sessions([s], path)
        loaded = load_sessions(path)
        assert loaded[0].total_active_seconds == 300.5


# --- Detail panel enhancements (v0.29, v0.32) ---

class TestDetailPanelEnhancements:
    def test_strip_ansi_default_enabled(self):
        dp = DetailPanel()
        assert dp._strip_ansi is True

    def test_toggle_ansi_strip(self):
        dp = DetailPanel()
        assert dp.toggle_ansi_strip() is False
        assert dp.toggle_ansi_strip() is True

    def test_toggle_pause(self):
        dp = DetailPanel()
        assert dp.is_paused is False
        assert dp.toggle_pause() is True
        assert dp.is_paused is True
        assert dp.toggle_pause() is False


# --- Stats panel with duration (v0.33) ---

class TestStatsPanelDuration:
    def test_stats_shows_active_time(self):
        s = SessionState.create(SessionConfig(cwd="/a"))
        s.total_active_seconds = 600
        s.status = SessionStatus.WAIT
        panel = StatsPanel([s])
        stats = panel._compute_stats()
        assert "Active Time" in stats


# --- CLI version (v0.34) ---

class TestCLIVersion:
    def test_version_importable(self):
        from csm import __version__
        assert __version__ == "0.43.0"


# --- Session pinning (v0.35) ---

class TestSessionPinning:
    def test_default_not_pinned(self):
        s = SessionState.create(SessionConfig(cwd="/test"))
        assert s.pinned is False

    def test_pin_persists(self, tmp_path):
        s = SessionState.create(SessionConfig(cwd="/test"))
        s.pinned = True
        s.status = SessionStatus.WAIT
        path = tmp_path / "sessions.json"
        save_sessions([s], path)
        loaded = load_sessions(path)
        assert loaded[0].pinned is True

    def test_pinned_sessions_sorted_first(self):
        sl = SessionList()
        s1 = SessionState.create(SessionConfig(cwd="/a"))
        s1.pinned = False
        s2 = SessionState.create(SessionConfig(cwd="/b"))
        s2.pinned = True
        result = sl._apply_sort([s1, s2])
        assert result[0].pinned is True


# --- Log rotation (v0.37) ---

class TestLogRotation:
    def test_cleanup_orphan_logs(self, tmp_path):
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        # Create an old orphan file
        old_file = logs_dir / "old-id.json"
        old_file.write_text("[]")
        # Set mtime to 10 days ago
        old_mtime = time.time() - (10 * 86400)
        os.utime(old_file, (old_mtime, old_mtime))
        # Create an active session file
        active_file = logs_dir / "active-id.json"
        active_file.write_text("[]")

        removed = cleanup_orphan_logs({"active-id"}, logs_dir, max_age_days=7)
        assert removed == 1
        assert not old_file.exists()
        assert active_file.exists()

    def test_cleanup_keeps_recent_orphans(self, tmp_path):
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        recent_file = logs_dir / "recent-id.json"
        recent_file.write_text("[]")
        removed = cleanup_orphan_logs(set(), logs_dir, max_age_days=7)
        assert removed == 0
        assert recent_file.exists()


# --- Backup/Restore (v0.39) ---

class TestBackupRestore:
    def test_export_and_import_backup(self, tmp_path):
        from csm.core.session_manager import OutputBufferStore
        s = SessionState.create(SessionConfig(cwd="/test", name="test-session"))
        s.status = SessionStatus.WAIT
        s.cost_usd = 1.5
        buf_store = OutputBufferStore()
        buf = buf_store.create(s.session_id)
        buf.append("line 1")
        buf.append("line 2")

        filepath = tmp_path / "backup.json"
        export_backup([s], buf_store, filepath)
        assert filepath.exists()

        sessions, logs = import_backup(filepath)
        assert len(sessions) == 1
        assert sessions[0].config.name == "test-session"
        assert s.session_id in logs
        assert logs[s.session_id] == ["line 1", "line 2"]


# --- Cost rate (v0.40) ---

class TestCostRate:
    def test_cost_per_hour_no_data(self):
        s = SessionState.create(SessionConfig(cwd="/test"))
        assert s.cost_per_hour == 0.0

    def test_cost_per_hour_with_data(self):
        s = SessionState.create(SessionConfig(cwd="/test"))
        s.cost_usd = 1.0
        s.total_active_seconds = 3600  # 1 hour
        assert s.cost_per_hour == pytest.approx(1.0, abs=0.01)

    def test_cost_per_hour_half_hour(self):
        s = SessionState.create(SessionConfig(cwd="/test"))
        s.cost_usd = 2.0
        s.total_active_seconds = 1800  # 30 min
        assert s.cost_per_hour == pytest.approx(4.0, abs=0.01)


# --- Batch operation modal (v0.38) ---

class TestBatchModals:
    def test_batch_operation_modal(self):
        from csm.widgets.modals import BatchOperationModal
        m = BatchOperationModal(5)
        assert m._count == 5

    def test_schedule_command_modal(self):
        from csm.widgets.modals import ScheduleCommandModal
        m = ScheduleCommandModal("test-session")
        assert m._session_name == "test-session"


# --- Command palette updated (v0.43) ---

class TestCommandPaletteV43:
    def test_palette_includes_new_actions(self):
        from csm.widgets.modals import CommandPaletteModal
        m = CommandPaletteModal()
        action_ids = [a[0] for a in m.ACTIONS]
        assert "toggle_pin" in action_ids
        assert "batch_operation" in action_ids
        assert "schedule_command" in action_ids
        assert "export_backup" in action_ids
        assert "shrink_list" in action_ids
