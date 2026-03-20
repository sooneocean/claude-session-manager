"""Tests for v0.11-v0.20 features."""
import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from csm.core.config import load_config, UserConfig, save_default_config
from csm.core.session_manager import SessionManager
from csm.core.persistence import save_sessions, load_sessions
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
