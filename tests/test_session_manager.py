"""Tests for SessionManager - T7"""
import asyncio
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from csm.core.session_manager import (
    SessionManager,
    DirectoryNotFoundError,
    DuplicateSessionError,
    SessionNotFoundError,
    OutputBufferStore,
)
from csm.models.session import SessionConfig, SessionStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MOCK_INIT_JSON = (
    '{"type":"system","subtype":"init","session_id":"test-sess-123","model":"claude-opus"}'
)
MOCK_RESULT_JSON = (
    '{"type":"result","total_cost_usd":0.05,'
    '"usage":{"input_tokens":10,"output_tokens":5},'
    '"result":"hello","session_id":"test-sess-123"}'
)


def make_mock_process(stdout_lines, returncode=0):
    """Create a mock process that supports streaming readline().

    stdout.readline() returns each line as bytes (with newline), then b"" for EOF.
    """
    proc = AsyncMock()
    # Build line-by-line byte responses for readline()
    lines_bytes = [line.encode() + b"\n" for line in stdout_lines] + [b""]
    readline_iter = iter(lines_bytes)
    proc.stdout = MagicMock()
    proc.stdout.readline = AsyncMock(side_effect=lambda: next(readline_iter))
    proc.returncode = returncode
    proc.wait = AsyncMock()
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    return proc


def make_success_process():
    return make_mock_process([MOCK_INIT_JSON, MOCK_RESULT_JSON])


def make_failing_process():
    return make_mock_process([MOCK_INIT_JSON, MOCK_RESULT_JSON], returncode=1)


def valid_cwd():
    """Return a directory that actually exists on this machine."""
    return os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# OutputBufferStore unit tests
# ---------------------------------------------------------------------------

class TestOutputBufferStore:
    def test_create_and_get(self):
        store = OutputBufferStore()
        buf = store.create("s1", capacity=10)
        assert store.get("s1") is buf

    def test_get_missing_returns_none(self):
        store = OutputBufferStore()
        assert store.get("nope") is None

    def test_remove(self):
        store = OutputBufferStore()
        store.create("s1")
        store.remove("s1")
        assert store.get("s1") is None

    def test_remove_missing_is_noop(self):
        store = OutputBufferStore()
        store.remove("ghost")  # should not raise


# ---------------------------------------------------------------------------
# SessionManager tests
# ---------------------------------------------------------------------------

@pytest.fixture
def manager():
    return SessionManager()


@pytest.fixture
def config():
    return SessionConfig(cwd=valid_cwd())


class TestSpawn:
    @pytest.mark.asyncio
    async def test_spawn_success(self, manager, config):
        proc = make_success_process()
        with patch("csm.core.session_manager.asyncio.create_subprocess_exec", return_value=proc):
            sid = await manager.spawn(config)
            await manager.flush()

        assert sid is not None
        state = manager.get_session(sid)
        assert state is not None
        assert state.status == SessionStatus.WAIT
        assert state.claude_session_id == "test-sess-123"
        assert state.cost_usd == pytest.approx(0.05)
        assert state.tokens_in == 10
        assert state.tokens_out == 5

    @pytest.mark.asyncio
    async def test_spawn_directory_not_found(self, manager):
        cfg = SessionConfig(cwd="/this/path/does/not/exist/ever")
        with pytest.raises(DirectoryNotFoundError):
            await manager.spawn(cfg)

    @pytest.mark.asyncio
    async def test_spawn_duplicate_session(self, manager, config):
        proc = make_success_process()
        with patch("csm.core.session_manager.asyncio.create_subprocess_exec", return_value=proc):
            await manager.spawn(config)
            await manager.flush()

        # Same cwd, same resume_id (both None) → duplicate
        proc2 = make_success_process()
        with patch("csm.core.session_manager.asyncio.create_subprocess_exec", return_value=proc2):
            with pytest.raises(DuplicateSessionError):
                await manager.spawn(config)

    @pytest.mark.asyncio
    async def test_spawn_returns_unique_ids(self, manager):
        cfg1 = SessionConfig(cwd=valid_cwd())
        cfg2 = SessionConfig(cwd=valid_cwd(), resume_id="different")

        proc1 = make_success_process()
        proc2 = make_success_process()
        with patch("csm.core.session_manager.asyncio.create_subprocess_exec", side_effect=[proc1, proc2]):
            sid1 = await manager.spawn(cfg1)
            sid2 = await manager.spawn(cfg2)
            await manager.flush()

        assert sid1 != sid2

    @pytest.mark.asyncio
    async def test_spawn_crash_marks_dead(self, manager, config):
        """Both initial attempt and retry fail → DEAD."""
        fail1 = make_failing_process()
        fail2 = make_failing_process()
        with patch("csm.core.session_manager.asyncio.create_subprocess_exec", side_effect=[fail1, fail2]):
            sid = await manager.spawn(config)
            await manager.flush()

        state = manager.get_session(sid)
        assert state.status == SessionStatus.DEAD

    @pytest.mark.asyncio
    async def test_spawn_session_limit(self, manager):
        """Cannot exceed SESSION_LIMIT active sessions."""
        async def do_spawn(i):
            cfg = SessionConfig(cwd=valid_cwd(), resume_id=str(i))
            proc = make_success_process()
            with patch("csm.core.session_manager.asyncio.create_subprocess_exec", return_value=proc):
                sid = await manager.spawn(cfg)
                await manager.flush()
                return sid

        for i in range(SessionManager.SESSION_LIMIT):
            await do_spawn(i)

        cfg_over = SessionConfig(cwd=valid_cwd(), resume_id="over")
        proc = make_success_process()
        with patch("csm.core.session_manager.asyncio.create_subprocess_exec", return_value=proc):
            with pytest.raises(RuntimeError, match="Session limit"):
                await manager.spawn(cfg_over)

    @pytest.mark.asyncio
    async def test_spawn_uses_resume_id_from_config(self, manager):
        """If config.resume_id is set and claude_session_id not yet known, --resume is passed."""
        cfg = SessionConfig(cwd=valid_cwd(), resume_id="existing-cli-session")
        proc = make_success_process()
        captured_cmd = []

        async def fake_exec(*args, **kwargs):
            captured_cmd.extend(args)
            return proc

        with patch("csm.core.session_manager.asyncio.create_subprocess_exec", side_effect=fake_exec):
            await manager.spawn(cfg)
            await manager.flush()

        assert "--resume" in captured_cmd
        idx = captured_cmd.index("--resume")
        assert captured_cmd[idx + 1] == "existing-cli-session"


class TestSendCommand:
    @pytest.mark.asyncio
    async def test_send_command_success(self, manager, config):
        proc = make_success_process()
        with patch("csm.core.session_manager.asyncio.create_subprocess_exec", return_value=proc):
            sid = await manager.spawn(config)
            await manager.flush()

        proc2 = make_mock_process(
            [MOCK_INIT_JSON,
             '{"type":"result","total_cost_usd":0.1,"usage":{"input_tokens":20,"output_tokens":10},'
             '"result":"done","session_id":"test-sess-123"}']
        )
        with patch("csm.core.session_manager.asyncio.create_subprocess_exec", return_value=proc2):
            await manager.send_command(sid, "do something")
            await manager.flush()

        state = manager.get_session(sid)
        assert state.status == SessionStatus.WAIT

    @pytest.mark.asyncio
    async def test_send_command_session_not_found(self, manager):
        with pytest.raises(SessionNotFoundError):
            await manager.send_command("nonexistent", "cmd")

    @pytest.mark.asyncio
    async def test_send_command_dead_session_raises(self, manager, config):
        fail1 = make_failing_process()
        fail2 = make_failing_process()
        with patch("csm.core.session_manager.asyncio.create_subprocess_exec", side_effect=[fail1, fail2]):
            sid = await manager.spawn(config)
            await manager.flush()

        state = manager.get_session(sid)
        assert state.status == SessionStatus.DEAD

        with pytest.raises(RuntimeError, match="DEAD"):
            await manager.send_command(sid, "cmd")

    @pytest.mark.asyncio
    async def test_send_command_crash_marks_dead(self, manager, config):
        proc = make_success_process()
        with patch("csm.core.session_manager.asyncio.create_subprocess_exec", return_value=proc):
            sid = await manager.spawn(config)
            await manager.flush()

        # send_command: first attempt fails, retry also fails → DEAD
        proc2 = make_failing_process()
        proc3 = make_failing_process()
        with patch("csm.core.session_manager.asyncio.create_subprocess_exec", side_effect=[proc2, proc3]):
            await manager.send_command(sid, "bad cmd")
            await manager.flush()

        assert manager.get_session(sid).status == SessionStatus.DEAD


class TestStop:
    @pytest.mark.asyncio
    async def test_stop_graceful(self, manager, config):
        proc = make_success_process()
        with patch("csm.core.session_manager.asyncio.create_subprocess_exec", return_value=proc):
            sid = await manager.spawn(config)
            await manager.flush()

        await manager.stop(sid)
        assert manager.get_session(sid).status == SessionStatus.DONE

    @pytest.mark.asyncio
    async def test_stop_session_not_found(self, manager):
        with pytest.raises(SessionNotFoundError):
            await manager.stop("ghost")

    @pytest.mark.asyncio
    async def test_stop_terminates_running_process(self, manager, config):
        """If a process is tracked in _running_processes, stop() terminates it."""
        proc = make_success_process()
        with patch("csm.core.session_manager.asyncio.create_subprocess_exec", return_value=proc):
            sid = await manager.spawn(config)
            await manager.flush()

        # Manually inject a "running" process to simulate mid-execution state
        fake_proc = MagicMock()
        fake_proc.returncode = None  # still running
        fake_proc.terminate = MagicMock()
        fake_proc.kill = MagicMock()
        fake_proc.wait = AsyncMock()
        manager._running_processes[sid] = fake_proc

        await manager.stop(sid)

        fake_proc.terminate.assert_called_once()


class TestRestart:
    @pytest.mark.asyncio
    async def test_restart_preserves_config(self, manager, config):
        proc = make_success_process()
        with patch("csm.core.session_manager.asyncio.create_subprocess_exec", return_value=proc):
            sid = await manager.spawn(config)
            await manager.flush()

        proc2 = make_success_process()
        with patch("csm.core.session_manager.asyncio.create_subprocess_exec", return_value=proc2):
            new_sid = await manager.restart(sid)
            await manager.flush()

        assert new_sid != sid
        new_state = manager.get_session(new_sid)
        assert new_state.config.cwd == config.cwd
        assert new_state.status == SessionStatus.WAIT

    @pytest.mark.asyncio
    async def test_restart_session_not_found(self, manager):
        with pytest.raises(SessionNotFoundError):
            await manager.restart("ghost")


class TestGetSessions:
    @pytest.mark.asyncio
    async def test_get_sessions_empty(self, manager):
        assert manager.get_sessions() == []

    @pytest.mark.asyncio
    async def test_get_sessions_returns_all(self, manager):
        cfg1 = SessionConfig(cwd=valid_cwd())
        cfg2 = SessionConfig(cwd=valid_cwd(), resume_id="r2")

        proc1, proc2 = make_success_process(), make_success_process()
        with patch("csm.core.session_manager.asyncio.create_subprocess_exec", side_effect=[proc1, proc2]):
            await manager.spawn(cfg1)
            await manager.spawn(cfg2)
            await manager.flush()

        sessions = manager.get_sessions()
        assert len(sessions) == 2


class TestCrashDetection:
    @pytest.mark.asyncio
    async def test_nonzero_exit_marks_dead(self, manager, config):
        fail1 = make_mock_process([MOCK_INIT_JSON, MOCK_RESULT_JSON], returncode=42)
        fail2 = make_mock_process([MOCK_INIT_JSON, MOCK_RESULT_JSON], returncode=42)
        with patch("csm.core.session_manager.asyncio.create_subprocess_exec", side_effect=[fail1, fail2]):
            sid = await manager.spawn(config)
            await manager.flush()

        assert manager.get_session(sid).status == SessionStatus.DEAD


class TestBufferIntegration:
    @pytest.mark.asyncio
    async def test_result_text_appended_to_buffer(self, manager, config):
        proc = make_success_process()
        with patch("csm.core.session_manager.asyncio.create_subprocess_exec", return_value=proc):
            sid = await manager.spawn(config)
            await manager.flush()

        buf = manager.buffer_store.get(sid)
        assert buf is not None
        lines = buf.get_lines()
        assert any("hello" in l for l in lines)


class TestShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_marks_all_done(self, manager):
        cfg1 = SessionConfig(cwd=valid_cwd())
        cfg2 = SessionConfig(cwd=valid_cwd(), resume_id="r2")

        proc1, proc2 = make_success_process(), make_success_process()
        with patch("csm.core.session_manager.asyncio.create_subprocess_exec", side_effect=[proc1, proc2]):
            sid1 = await manager.spawn(cfg1)
            sid2 = await manager.spawn(cfg2)
            await manager.flush()

        await manager.shutdown()

        assert manager.get_session(sid1).status == SessionStatus.DONE
        assert manager.get_session(sid2).status == SessionStatus.DONE
