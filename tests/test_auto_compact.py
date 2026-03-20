"""Tests for auto-compact feature."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from csm.core.session_manager import SessionManager
from csm.models.session import SessionConfig, SessionStatus


MOCK_INIT = '{"type":"system","subtype":"init","session_id":"compact-001","model":"opus"}'
MOCK_RESULT = '{"type":"result","total_cost_usd":0.1,"usage":{"input_tokens":10,"output_tokens":5},"result":"ok","session_id":"compact-001"}'
MOCK_RESULT_HIGH_TOKENS = '{"type":"result","total_cost_usd":5.0,"usage":{"input_tokens":30000,"output_tokens":25000},"result":"done","session_id":"compact-001"}'
MOCK_COMPACT_RESULT = '{"type":"result","total_cost_usd":0.01,"usage":{"input_tokens":100,"output_tokens":50},"result":"Compacted context","session_id":"compact-001"}'


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


class TestAutoCompact:
    @pytest.mark.asyncio
    @patch("csm.core.session_manager.asyncio.create_subprocess_exec")
    @patch("csm.core.session_manager.os.path.isdir", return_value=True)
    async def test_no_compact_below_threshold(self, mock_isdir, mock_exec):
        """Normal token usage should not trigger compact."""
        mock_exec.side_effect = [
            make_mock_process([MOCK_INIT, MOCK_RESULT]),  # spawn
            make_mock_process([MOCK_INIT, MOCK_RESULT]),  # send_command
        ]

        manager = SessionManager()
        sid = await manager.spawn(SessionConfig(cwd="/test"))
        await manager.flush()

        # Send a command with low tokens
        await manager.send_command(sid, "hello")
        await manager.flush()

        session = manager.get_session(sid)
        # tokens should be small, no compact triggered
        assert session.tokens_in < manager.AUTO_COMPACT_TOKEN_THRESHOLD
        # Only 2 subprocess calls (spawn + send_command), no compact
        assert mock_exec.call_count == 2
        await manager.shutdown()

    @pytest.mark.asyncio
    @patch("csm.core.session_manager.asyncio.create_subprocess_exec")
    @patch("csm.core.session_manager.os.path.isdir", return_value=True)
    async def test_compact_triggered_above_threshold(self, mock_isdir, mock_exec):
        """High token usage should trigger auto-compact."""
        mock_exec.side_effect = [
            make_mock_process([MOCK_INIT, MOCK_RESULT]),  # spawn
            make_mock_process([MOCK_INIT, MOCK_RESULT_HIGH_TOKENS]),  # send_command (high tokens)
            make_mock_process([MOCK_INIT, MOCK_COMPACT_RESULT]),  # auto-compact
        ]

        manager = SessionManager()
        sid = await manager.spawn(SessionConfig(cwd="/test"))
        await manager.flush()

        await manager.send_command(sid, "big task")
        await manager.flush()

        session = manager.get_session(sid)
        # After compact, tokens should be reset
        assert session.tokens_in == 0
        assert session.tokens_out == 0
        assert session.status == SessionStatus.WAIT
        # 3 calls: spawn + send_command + auto-compact
        assert mock_exec.call_count == 3
        await manager.shutdown()

    def test_threshold_constant(self):
        assert SessionManager.AUTO_COMPACT_TOKEN_THRESHOLD == 50000
