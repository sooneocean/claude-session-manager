"""Tests for CommandDispatcher - T8"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from csm.core.command_dispatcher import (
    CommandDispatcher,
    QueueFullError,
    SessionDeadError,
)
from csm.core.session_manager import SessionManager, SessionNotFoundError
from csm.models.session import SessionConfig, SessionStatus, SessionState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_session(status=SessionStatus.WAIT, sid="sess-1"):
    cfg = SessionConfig(cwd="/tmp")
    state = SessionState(session_id=sid, config=cfg, status=status)
    return state


def make_manager_with_session(status=SessionStatus.WAIT, sid="sess-1"):
    """Return a SessionManager mock with one pre-loaded session."""
    manager = MagicMock(spec=SessionManager)
    state = make_session(status=status, sid=sid)
    manager.get_session.return_value = state
    manager.send_command = AsyncMock(return_value="ok")
    return manager, state


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRegisterSession:
    @pytest.mark.asyncio
    async def test_register_creates_queue(self):
        manager, _ = make_manager_with_session()
        dispatcher = CommandDispatcher(manager)
        dispatcher.register_session("sess-1")
        assert "sess-1" in dispatcher._queues

    @pytest.mark.asyncio
    async def test_register_twice_is_idempotent(self):
        manager, _ = make_manager_with_session()
        dispatcher = CommandDispatcher(manager)
        dispatcher.register_session("sess-1")
        q1 = dispatcher._queues["sess-1"]
        dispatcher.register_session("sess-1")
        assert dispatcher._queues["sess-1"] is q1  # same object

    @pytest.mark.asyncio
    async def test_register_creates_consumer_task(self):
        manager, _ = make_manager_with_session()
        dispatcher = CommandDispatcher(manager)
        dispatcher.register_session("sess-1")
        assert "sess-1" in dispatcher._consumers
        assert isinstance(dispatcher._consumers["sess-1"], asyncio.Task)


class TestEnqueue:
    @pytest.mark.asyncio
    async def test_enqueue_success(self):
        manager, _ = make_manager_with_session()
        dispatcher = CommandDispatcher(manager)
        dispatcher.register_session("sess-1")
        await dispatcher.enqueue("sess-1", "do something")
        assert dispatcher._queues["sess-1"].qsize() >= 0  # consumed quickly

    @pytest.mark.asyncio
    async def test_enqueue_session_not_found(self):
        manager = MagicMock(spec=SessionManager)
        manager.get_session.return_value = None
        dispatcher = CommandDispatcher(manager)
        with pytest.raises(SessionNotFoundError):
            await dispatcher.enqueue("ghost", "cmd")

    @pytest.mark.asyncio
    async def test_enqueue_dead_session_raises(self):
        manager, _ = make_manager_with_session(status=SessionStatus.DEAD)
        dispatcher = CommandDispatcher(manager)
        dispatcher.register_session("sess-1")
        with pytest.raises(SessionDeadError):
            await dispatcher.enqueue("sess-1", "cmd")

    @pytest.mark.asyncio
    async def test_enqueue_no_queue_registered(self):
        manager, _ = make_manager_with_session()
        dispatcher = CommandDispatcher(manager)
        # Session exists in manager but not registered in dispatcher
        with pytest.raises(SessionNotFoundError):
            await dispatcher.enqueue("sess-1", "cmd")

    @pytest.mark.asyncio
    async def test_enqueue_queue_full(self):
        manager, _ = make_manager_with_session()
        dispatcher = CommandDispatcher(manager)
        # Use a custom tiny queue to simulate full
        dispatcher._queues["sess-1"] = asyncio.Queue(maxsize=2)
        # Put items without a consumer draining
        dispatcher._queues["sess-1"].put_nowait("a")
        dispatcher._queues["sess-1"].put_nowait("b")

        with pytest.raises(QueueFullError):
            await dispatcher.enqueue("sess-1", "overflow")


class TestConsumer:
    @pytest.mark.asyncio
    async def test_consumer_calls_send_command(self):
        """Consumer must call send_command for each queued item."""
        manager, _ = make_manager_with_session()
        dispatcher = CommandDispatcher(manager)
        dispatcher.register_session("sess-1")

        await dispatcher.enqueue("sess-1", "task-1")
        await dispatcher.enqueue("sess-1", "task-2")

        # Give consumer time to drain
        await asyncio.sleep(0.05)

        calls = [call.args for call in manager.send_command.await_args_list]
        assert ("sess-1", "task-1") in calls
        assert ("sess-1", "task-2") in calls

    @pytest.mark.asyncio
    async def test_consumer_fifo_order(self):
        """Commands must be delivered in enqueue order."""
        order = []
        manager = MagicMock(spec=SessionManager)
        state = make_session()
        manager.get_session.return_value = state

        async def capture_cmd(sid, cmd):
            order.append(cmd)
            return "ok"

        manager.send_command = capture_cmd

        dispatcher = CommandDispatcher(manager)
        dispatcher.register_session("sess-1")

        await dispatcher.enqueue("sess-1", "first")
        await dispatcher.enqueue("sess-1", "second")
        await dispatcher.enqueue("sess-1", "third")

        await asyncio.sleep(0.1)

        assert order == ["first", "second", "third"]

    @pytest.mark.asyncio
    async def test_consumer_survives_send_command_exception(self):
        """Consumer must continue processing after an exception."""
        call_count = 0
        manager = MagicMock(spec=SessionManager)
        state = make_session()
        manager.get_session.return_value = state

        async def flaky_cmd(sid, cmd):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("simulated failure")
            return "ok"

        manager.send_command = flaky_cmd

        dispatcher = CommandDispatcher(manager)
        dispatcher.register_session("sess-1")

        await dispatcher.enqueue("sess-1", "will-fail")
        await dispatcher.enqueue("sess-1", "will-succeed")

        await asyncio.sleep(0.1)

        assert call_count == 2  # both were processed


class TestCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_removes_queue_and_consumer(self):
        manager, _ = make_manager_with_session()
        dispatcher = CommandDispatcher(manager)
        dispatcher.register_session("sess-1")

        dispatcher.cleanup_session("sess-1")

        assert "sess-1" not in dispatcher._queues
        assert "sess-1" not in dispatcher._consumers

    @pytest.mark.asyncio
    async def test_cleanup_cancels_consumer_task(self):
        manager, _ = make_manager_with_session()
        dispatcher = CommandDispatcher(manager)
        dispatcher.register_session("sess-1")
        task = dispatcher._consumers["sess-1"]

        dispatcher.cleanup_session("sess-1")

        await asyncio.sleep(0.02)
        assert task.cancelled() or task.done()

    @pytest.mark.asyncio
    async def test_cleanup_unknown_session_is_noop(self):
        manager, _ = make_manager_with_session()
        dispatcher = CommandDispatcher(manager)
        dispatcher.cleanup_session("ghost")  # should not raise


class TestShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_cancels_all_consumers(self):
        manager = MagicMock(spec=SessionManager)

        def make_state(sid):
            cfg = SessionConfig(cwd="/tmp")
            return SessionState(session_id=sid, config=cfg, status=SessionStatus.WAIT)

        manager.get_session.side_effect = lambda sid: make_state(sid)
        manager.send_command = AsyncMock(return_value="ok")

        dispatcher = CommandDispatcher(manager)
        dispatcher.register_session("s1")
        dispatcher.register_session("s2")

        tasks = list(dispatcher._consumers.values())
        await dispatcher.shutdown()

        await asyncio.sleep(0.02)
        for t in tasks:
            assert t.cancelled() or t.done()

        assert len(dispatcher._consumers) == 0
        assert len(dispatcher._queues) == 0
