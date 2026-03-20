"""T13: Integration tests for Claude Session Manager.

Tests the full lifecycle of the application components working together.
Uses mock subprocess to avoid spawning real claude processes.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from csm.core.session_manager import SessionManager, OutputBufferStore
from csm.core.command_dispatcher import CommandDispatcher
from csm.core.output_parser import OutputParser
from csm.models.session import SessionConfig, SessionStatus
from csm.models.cost import CostAggregator

# --- Mock helpers ---

MOCK_INIT = '{"type":"system","subtype":"init","session_id":"integ-sess-001","model":"claude-opus-4-6[1m]"}'
MOCK_RESULT = '{"type":"result","total_cost_usd":0.12,"usage":{"input_tokens":50,"output_tokens":25},"result":"Integration test response","session_id":"integ-sess-001"}'
MOCK_RESULT_SOP = '{"type":"result","total_cost_usd":0.25,"usage":{"input_tokens":100,"output_tokens":50},"result":"Launching skill: s4-implement - starting implementation","session_id":"integ-sess-001"}'
MOCK_CRASH_RESULT = '{"type":"result","total_cost_usd":0.01,"usage":{"input_tokens":5,"output_tokens":2},"result":"error","session_id":"integ-sess-001"}'


def make_mock_process(stdout_lines, returncode=0):
    proc = AsyncMock()
    lines_bytes = [line.encode("utf-8") + b"\n" for line in stdout_lines] + [b""]
    readline_iter = iter(lines_bytes)
    proc.stdout = MagicMock()
    proc.stdout.readline = AsyncMock(side_effect=lambda: next(readline_iter))
    proc.returncode = returncode
    proc.wait = AsyncMock()
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    return proc


# --- Integration Tests ---

class TestFullLifecycle:
    """Test the complete session lifecycle: spawn → command → stop."""

    @pytest.mark.asyncio
    @patch("csm.core.session_manager.asyncio.create_subprocess_exec")
    @patch("csm.core.session_manager.os.path.isdir", return_value=True)
    async def test_spawn_command_stop(self, mock_isdir, mock_exec):
        """Full lifecycle: spawn → send command → stop."""
        mock_exec.side_effect = [
            make_mock_process([MOCK_INIT, MOCK_RESULT]),  # spawn
            make_mock_process([MOCK_INIT, MOCK_RESULT]),  # send_command
        ]

        manager = SessionManager()
        dispatcher = CommandDispatcher(manager)

        # Spawn
        config = SessionConfig(cwd="/test/project")
        sid = await manager.spawn(config)
        dispatcher.register_session(sid)
        await manager.flush()

        session = manager.get_session(sid)
        assert session is not None
        assert session.status == SessionStatus.WAIT
        assert session.claude_session_id == "integ-sess-001"
        assert session.cost_usd == 0.12

        # Send command
        await manager.send_command(sid, "do something")
        await manager.flush()
        assert session.status == SessionStatus.WAIT

        # Stop
        await manager.stop(sid)
        assert session.status == SessionStatus.DONE

        # Cleanup
        await dispatcher.shutdown()

    @pytest.mark.asyncio
    @patch("csm.core.session_manager.asyncio.create_subprocess_exec")
    @patch("csm.core.session_manager.os.path.isdir", return_value=True)
    async def test_spawn_crash_restart(self, mock_isdir, mock_exec):
        """Lifecycle with crash and restart."""
        mock_exec.side_effect = [
            make_mock_process([MOCK_INIT, MOCK_CRASH_RESULT], returncode=1),  # spawn → crash (attempt 1)
            make_mock_process([MOCK_INIT, MOCK_CRASH_RESULT], returncode=1),  # spawn → crash (retry)
            make_mock_process([MOCK_INIT, MOCK_RESULT]),  # restart → success (attempt 1)
        ]

        manager = SessionManager()

        # Spawn (will crash)
        config = SessionConfig(cwd="/test/project")
        sid = await manager.spawn(config)
        await manager.flush()
        session = manager.get_session(sid)
        assert session.status == SessionStatus.DEAD

        # Restart
        new_sid = await manager.restart(sid)
        await manager.flush()
        new_session = manager.get_session(new_sid)
        assert new_session is not None
        assert new_session.status == SessionStatus.WAIT
        # Path gets normalized by SessionManager (expanduser + abspath)
        import os
        assert new_session.config.cwd == os.path.abspath("/test/project")

        await manager.shutdown()


class TestCostTracking:
    """Test cost aggregation across multiple sessions."""

    @pytest.mark.asyncio
    @patch("csm.core.session_manager.asyncio.create_subprocess_exec")
    @patch("csm.core.session_manager.os.path.isdir", return_value=True)
    async def test_cost_accumulates_across_sessions(self, mock_isdir, mock_exec):
        mock_result_a = '{"type":"result","total_cost_usd":1.50,"usage":{"input_tokens":100,"output_tokens":50},"result":"done a","session_id":"sess-a"}'
        mock_result_b = '{"type":"result","total_cost_usd":2.00,"usage":{"input_tokens":200,"output_tokens":100},"result":"done b","session_id":"sess-b"}'

        mock_exec.side_effect = [
            make_mock_process([MOCK_INIT, mock_result_a]),
            make_mock_process([MOCK_INIT, mock_result_b]),
        ]

        manager = SessionManager()

        sid_a = await manager.spawn(SessionConfig(cwd="/project-a"))
        sid_b = await manager.spawn(SessionConfig(cwd="/project-b"))
        await manager.flush()

        total = manager.cost_aggregator.get_total()
        assert total.total_cost_usd == pytest.approx(3.50, abs=0.01)
        assert total.session_count == 2

        await manager.shutdown()


class TestSOPDetection:
    """Test SOP stage detection from stream-json output."""

    @pytest.mark.asyncio
    @patch("csm.core.session_manager.asyncio.create_subprocess_exec")
    @patch("csm.core.session_manager.os.path.isdir", return_value=True)
    async def test_sop_stage_detected(self, mock_isdir, mock_exec):
        mock_exec.return_value = make_mock_process([MOCK_INIT, MOCK_RESULT_SOP])

        manager = SessionManager()
        sid = await manager.spawn(SessionConfig(cwd="/test"))
        await manager.flush()

        session = manager.get_session(sid)
        assert session.sop_stage == "S4"

        await manager.shutdown()


class TestOutputBufferIntegration:
    """Test that output is correctly stored in ring buffers."""

    @pytest.mark.asyncio
    @patch("csm.core.session_manager.asyncio.create_subprocess_exec")
    @patch("csm.core.session_manager.os.path.isdir", return_value=True)
    async def test_output_stored_in_buffer(self, mock_isdir, mock_exec):
        mock_exec.return_value = make_mock_process([MOCK_INIT, MOCK_RESULT])

        manager = SessionManager()
        sid = await manager.spawn(SessionConfig(cwd="/test"))
        await manager.flush()

        buf = manager.buffer_store.get(sid)
        assert buf is not None
        lines = buf.get_lines()
        assert len(lines) > 0
        assert "Integration test response" in "\n".join(lines)

        await manager.shutdown()


class TestMultipleSessions:
    """Test managing multiple sessions concurrently."""

    @pytest.mark.asyncio
    @patch("csm.core.session_manager.asyncio.create_subprocess_exec")
    @patch("csm.core.session_manager.os.path.isdir", return_value=True)
    async def test_multiple_sessions_independent(self, mock_isdir, mock_exec):
        results = [
            make_mock_process([MOCK_INIT, '{"type":"result","total_cost_usd":0.1,"usage":{"input_tokens":10,"output_tokens":5},"result":"resp1","session_id":"s1"}']),
            make_mock_process([MOCK_INIT, '{"type":"result","total_cost_usd":0.2,"usage":{"input_tokens":20,"output_tokens":10},"result":"resp2","session_id":"s2"}']),
            make_mock_process([MOCK_INIT, '{"type":"result","total_cost_usd":0.3,"usage":{"input_tokens":30,"output_tokens":15},"result":"resp3","session_id":"s3"}']),
        ]
        mock_exec.side_effect = results

        manager = SessionManager()

        sids = []
        for i in range(3):
            sid = await manager.spawn(SessionConfig(cwd=f"/project-{i}"))
            sids.append(sid)
        await manager.flush()

        sessions = manager.get_sessions()
        assert len(sessions) == 3

        # Each session has independent state
        for s in sessions:
            assert s.status == SessionStatus.WAIT

        # Stop one doesn't affect others
        await manager.stop(sids[1])
        active = [s for s in manager.get_sessions() if s.status == SessionStatus.WAIT]
        assert len(active) == 2

        await manager.shutdown()


class TestCommandDispatcherIntegration:
    """Test CommandDispatcher with SessionManager."""

    @pytest.mark.asyncio
    @patch("csm.core.session_manager.asyncio.create_subprocess_exec")
    @patch("csm.core.session_manager.os.path.isdir", return_value=True)
    async def test_enqueue_and_consume(self, mock_isdir, mock_exec):
        mock_exec.side_effect = [
            make_mock_process([MOCK_INIT, MOCK_RESULT]),  # spawn
            make_mock_process([MOCK_INIT, MOCK_RESULT]),  # command
        ]

        manager = SessionManager()
        dispatcher = CommandDispatcher(manager)

        sid = await manager.spawn(SessionConfig(cwd="/test"))
        await manager.flush()
        dispatcher.register_session(sid)

        await dispatcher.enqueue(sid, "test command")
        # Give consumer task time to process
        await asyncio.sleep(0.5)
        await manager.flush()

        session = manager.get_session(sid)
        assert session is not None

        dispatcher.cleanup_session(sid)
        await dispatcher.shutdown()
        await manager.shutdown()


class TestKeyboardNavigation:
    """Test keyboard shortcut handling in the app."""

    @pytest.mark.asyncio
    async def test_app_can_start_and_quit(self):
        """Basic smoke test: app starts and can be quit."""
        from csm.app import CSMApp

        app = CSMApp()
        async with app.run_test() as pilot:
            # App should be running
            assert app.is_running
            # Press q to quit
            await pilot.press("q")
