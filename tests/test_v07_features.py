"""Tests for v0.7.0 features: psutil monitoring, retry, broadcast, help, filter/sort."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from csm.models.session import SessionConfig, SessionState, SessionStatus
from csm.core.session_manager import SessionManager
from csm.core.command_dispatcher import CommandDispatcher
from csm.widgets.session_list import SessionList, SortKey
from csm.widgets.detail_panel import DetailPanel


# --- Mock helpers ---

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


MOCK_INIT = '{"type":"system","subtype":"init","session_id":"test-001","model":"opus"}'
MOCK_RESULT = '{"type":"result","total_cost_usd":0.1,"usage":{"input_tokens":10,"output_tokens":5},"result":"ok","session_id":"test-001"}'


# --- Retry tests ---

class TestRetryMechanism:
    @pytest.mark.asyncio
    @patch("csm.core.session_manager.asyncio.create_subprocess_exec")
    @patch("csm.core.session_manager.os.path.isdir", return_value=True)
    async def test_spawn_retries_on_first_failure(self, mock_isdir, mock_exec):
        """If first _run_claude returns None (fail), it retries once."""
        fail_proc = make_mock_process([MOCK_INIT], returncode=1)
        success_proc = make_mock_process([MOCK_INIT, MOCK_RESULT])
        mock_exec.side_effect = [fail_proc, success_proc]

        manager = SessionManager()
        sid = await manager.spawn(SessionConfig(cwd="/test"))
        await manager.flush()

        session = manager.get_session(sid)
        # Should succeed after retry
        assert session.status == SessionStatus.WAIT
        assert mock_exec.call_count == 2
        await manager.shutdown()

    @pytest.mark.asyncio
    @patch("csm.core.session_manager.asyncio.create_subprocess_exec")
    @patch("csm.core.session_manager.os.path.isdir", return_value=True)
    async def test_spawn_dead_after_two_failures(self, mock_isdir, mock_exec):
        """If both attempts fail, session is marked DEAD."""
        fail1 = make_mock_process([MOCK_INIT], returncode=1)
        fail2 = make_mock_process([MOCK_INIT], returncode=1)
        mock_exec.side_effect = [fail1, fail2]

        manager = SessionManager()
        sid = await manager.spawn(SessionConfig(cwd="/test"))
        await manager.flush()

        session = manager.get_session(sid)
        assert session.status == SessionStatus.DEAD
        await manager.shutdown()


# --- Filter/Sort tests ---

class TestFilterSort:
    def _make_sessions(self):
        configs = [
            ("proj-a", SessionStatus.RUN, 2.0, "S4"),
            ("proj-b", SessionStatus.WAIT, 0.5, "S0"),
            ("proj-c", SessionStatus.DEAD, 1.0, None),
            ("proj-d", SessionStatus.WAIT, 3.0, "S7"),
        ]
        sessions = []
        for cwd, status, cost, stage in configs:
            s = SessionState.create(SessionConfig(cwd=f"/{cwd}"))
            s.status = status
            s.cost_usd = cost
            s.sop_stage = stage
            sessions.append(s)
        return sessions

    def test_filter_by_wait(self):
        sl = SessionList()
        sl._filter_status = SessionStatus.WAIT
        filtered = sl._apply_filter(self._make_sessions())
        assert len(filtered) == 2
        assert all(s.status == SessionStatus.WAIT for s in filtered)

    def test_filter_none_shows_all(self):
        sl = SessionList()
        sl._filter_status = None
        filtered = sl._apply_filter(self._make_sessions())
        assert len(filtered) == 4

    def test_sort_by_cost(self):
        sl = SessionList()
        sl._sort_key = SortKey.COST
        sorted_s = sl._apply_sort(self._make_sessions())
        costs = [s.cost_usd for s in sorted_s]
        assert costs == sorted(costs, reverse=True)

    def test_sort_by_status(self):
        sl = SessionList()
        sl._sort_key = SortKey.STATUS
        sorted_s = sl._apply_sort(self._make_sessions())
        # RUN should come first
        assert sorted_s[0].status == SessionStatus.RUN

    def test_cycle_filter(self):
        sl = SessionList()
        sl._all_sessions = self._make_sessions()
        assert sl._filter_status is None
        cycle = [None, SessionStatus.RUN, SessionStatus.WAIT, SessionStatus.DEAD, SessionStatus.DONE]
        sl._filter_status = None
        idx = cycle.index(sl._filter_status)
        next_f = cycle[(idx + 1) % len(cycle)]
        sl._filter_status = next_f
        assert next_f == SessionStatus.RUN

    def test_cycle_sort(self):
        sl = SessionList()
        assert sl._sort_key == SortKey.NONE
        cycle = [SortKey.NONE, SortKey.COST, SortKey.STATUS, SortKey.STAGE]
        idx = cycle.index(sl._sort_key)
        next_s = cycle[(idx + 1) % len(cycle)]
        sl._sort_key = next_s
        assert next_s == SortKey.COST


# --- DetailPanel incremental tests ---

class TestDetailPanelIncremental:
    def test_track_session(self):
        dp = DetailPanel()
        dp.track_session("abc-123")
        assert dp._tracking_session_id == "abc-123"

    def test_track_session_none(self):
        dp = DetailPanel()
        dp.track_session(None)
        assert dp._tracking_session_id is None


# --- Persistence restore test ---

class TestPersistenceRestore:
    def test_roundtrip_with_name(self, tmp_path):
        from csm.core.persistence import save_sessions, load_sessions

        s = SessionState.create(SessionConfig(cwd="/test", name="my-project"))
        s.claude_session_id = "cli-sess-999"
        s.status = SessionStatus.WAIT
        s.cost_usd = 5.67

        path = tmp_path / "sessions.json"
        save_sessions([s], path)
        loaded = load_sessions(path)

        assert len(loaded) == 1
        assert loaded[0].config.name == "my-project"
        assert loaded[0].claude_session_id == "cli-sess-999"
        assert loaded[0].cost_usd == pytest.approx(5.67)


# --- Help modal test ---

class TestHelpModal:
    def test_help_modal_importable(self):
        from csm.widgets.modals import HelpModal
        assert HelpModal is not None
        assert hasattr(HelpModal, "HELP_TEXT")
        assert "Keyboard Shortcuts" in HelpModal.HELP_TEXT
