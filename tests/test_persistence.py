"""Tests for session persistence (save/load)."""
import json
import os
import pytest
from pathlib import Path

from csm.core.persistence import save_sessions, load_sessions
from csm.models.session import SessionState, SessionConfig, SessionStatus


@pytest.fixture
def tmp_path_file(tmp_path):
    return tmp_path / "sessions.json"


@pytest.fixture
def sample_sessions():
    s1 = SessionState.create(SessionConfig(cwd="/project-a", model="sonnet"))
    s1.claude_session_id = "claude-abc-123"
    s1.status = SessionStatus.WAIT
    s1.sop_stage = "S4"
    s1.tokens_in = 100
    s1.tokens_out = 50
    s1.cost_usd = 1.23

    s2 = SessionState.create(SessionConfig(cwd="/project-b", resume_id="old-sess"))
    s2.claude_session_id = "claude-def-456"
    s2.status = SessionStatus.DEAD
    s2.cost_usd = 0.45

    return [s1, s2]


class TestSaveSessions:
    def test_save_creates_file(self, tmp_path_file, sample_sessions):
        save_sessions(sample_sessions, tmp_path_file)
        assert tmp_path_file.exists()

    def test_save_valid_json(self, tmp_path_file, sample_sessions):
        save_sessions(sample_sessions, tmp_path_file)
        data = json.loads(tmp_path_file.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 2

    def test_save_contains_required_fields(self, tmp_path_file, sample_sessions):
        save_sessions(sample_sessions, tmp_path_file)
        data = json.loads(tmp_path_file.read_text(encoding="utf-8"))
        entry = data[0]
        assert "config" in entry
        assert "claude_session_id" in entry
        assert "status" in entry
        assert "cost_usd" in entry
        assert "tokens_in" in entry

    def test_save_empty_list(self, tmp_path_file):
        save_sessions([], tmp_path_file)
        data = json.loads(tmp_path_file.read_text(encoding="utf-8"))
        assert data == []

    def test_save_creates_parent_dirs(self, tmp_path):
        nested = tmp_path / "deep" / "nested" / "sessions.json"
        save_sessions([], nested)
        assert nested.exists()


class TestLoadSessions:
    def test_load_missing_file_returns_empty(self, tmp_path_file):
        result = load_sessions(tmp_path_file)
        assert result == []

    def test_load_corrupt_json_returns_empty(self, tmp_path_file):
        tmp_path_file.write_text("not valid json {{{", encoding="utf-8")
        result = load_sessions(tmp_path_file)
        assert result == []

    def test_load_empty_array_returns_empty(self, tmp_path_file):
        tmp_path_file.write_text("[]", encoding="utf-8")
        result = load_sessions(tmp_path_file)
        assert result == []


class TestRoundTrip:
    def test_save_then_load_preserves_data(self, tmp_path_file, sample_sessions):
        save_sessions(sample_sessions, tmp_path_file)
        loaded = load_sessions(tmp_path_file)

        assert len(loaded) == 2

        s1 = loaded[0]
        assert s1.config.cwd == "/project-a"
        assert s1.config.model == "sonnet"
        assert s1.claude_session_id == "claude-abc-123"
        assert s1.status == SessionStatus.WAIT
        assert s1.sop_stage == "S4"
        assert s1.tokens_in == 100
        assert s1.tokens_out == 50
        assert s1.cost_usd == pytest.approx(1.23)

        s2 = loaded[1]
        assert s2.config.cwd == "/project-b"
        assert s2.config.resume_id == "old-sess"
        assert s2.status == SessionStatus.DEAD

    def test_roundtrip_preserves_session_id(self, tmp_path_file, sample_sessions):
        original_ids = [s.session_id for s in sample_sessions]
        save_sessions(sample_sessions, tmp_path_file)
        loaded = load_sessions(tmp_path_file)
        loaded_ids = [s.session_id for s in loaded]
        assert loaded_ids == original_ids
