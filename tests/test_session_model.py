"""Tests for Session data models - T4"""
import pytest
from datetime import datetime
from csm.models.session import SessionConfig, SessionState, SessionStatus


class TestSessionStatusEnum:

    def test_session_status_enum_values(self):
        assert SessionStatus.STARTING.value == "STARTING"
        assert SessionStatus.RUN.value == "RUN"
        assert SessionStatus.WAIT.value == "WAIT"
        assert SessionStatus.DONE.value == "DONE"
        assert SessionStatus.DEAD.value == "DEAD"


class TestSessionConfig:

    def test_session_config_defaults(self):
        config = SessionConfig(cwd="/tmp")
        assert config.cwd == "/tmp"
        assert config.resume_id is None
        assert config.model is None
        assert config.permission_mode == "auto"
        assert config.name is None
        assert config.max_budget_usd is None

    def test_session_config_custom(self):
        config = SessionConfig(
            cwd="/workspace",
            resume_id="sess-123",
            model="claude-opus-4",
            permission_mode="manual",
            name="my-session",
            max_budget_usd=5.0,
        )
        assert config.cwd == "/workspace"
        assert config.resume_id == "sess-123"
        assert config.model == "claude-opus-4"
        assert config.permission_mode == "manual"
        assert config.name == "my-session"
        assert config.max_budget_usd == 5.0


class TestSessionState:

    def test_session_state_create(self):
        config = SessionConfig(cwd="/tmp")
        state = SessionState.create(config)

        assert state.session_id is not None
        assert len(state.session_id) > 0  # uuid4 string
        assert state.config is config
        assert state.status == SessionStatus.STARTING
        assert state.claude_session_id is None
        assert state.sop_stage is None
        assert state.exit_code is None
        assert state.pid is None
        assert state.tokens_in == 0
        assert state.tokens_out == 0
        assert state.cost_usd == 0.0
        assert state.last_result == ""

    def test_session_state_create_with_resume(self):
        config = SessionConfig(cwd="/tmp", resume_id="existing-session-id")
        state = SessionState.create(config)

        # session_id is a new UUID, not the resume_id
        assert state.session_id != "existing-session-id"
        # resume_id is stored in config
        assert state.config.resume_id == "existing-session-id"

    def test_session_state_fields_typed(self):
        config = SessionConfig(cwd="/project")
        state = SessionState.create(config)

        assert isinstance(state.session_id, str)
        assert isinstance(state.config, SessionConfig)
        assert isinstance(state.status, SessionStatus)
        assert isinstance(state.started_at, datetime)
        assert isinstance(state.last_activity, datetime)
        assert isinstance(state.tokens_in, int)
        assert isinstance(state.tokens_out, int)
        assert isinstance(state.cost_usd, float)
        assert isinstance(state.last_result, str)

    def test_session_state_unique_ids(self):
        config = SessionConfig(cwd="/tmp")
        state1 = SessionState.create(config)
        state2 = SessionState.create(config)
        assert state1.session_id != state2.session_id
