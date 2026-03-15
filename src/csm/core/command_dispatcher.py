"""CommandDispatcher - serializes command dispatch per session. T8"""
import asyncio
import logging

from csm.core.session_manager import SessionManager, SessionNotFoundError
from csm.models.session import SessionStatus

logger = logging.getLogger(__name__)


class QueueFullError(Exception):
    """Raised when a session's command queue has reached its capacity."""


class SessionDeadError(Exception):
    """Raised when attempting to enqueue a command to a DEAD session."""


class CommandDispatcher:
    """Serializes command dispatch to sessions.

    Each registered session gets its own asyncio.Queue and a long-running
    consumer task that pulls commands one-at-a-time and forwards them to
    SessionManager.send_command.  This guarantees that no two commands run
    concurrently against the same Claude CLI session.
    """

    QUEUE_MAX_SIZE = 50

    def __init__(self, session_manager: SessionManager) -> None:
        self._manager = session_manager
        self._queues: dict[str, asyncio.Queue] = {}
        self._consumers: dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_session(self, session_id: str) -> None:
        """Create a command queue and start a consumer task for *session_id*.

        Calling this method more than once for the same session_id is safe —
        the second call is a no-op.
        """
        if session_id in self._queues:
            return
        self._queues[session_id] = asyncio.Queue(maxsize=self.QUEUE_MAX_SIZE)
        self._consumers[session_id] = asyncio.create_task(
            self._consume(session_id),
            name=f"dispatcher-consumer-{session_id}",
        )

    async def enqueue(self, session_id: str, command: str) -> None:
        """Add *command* to *session_id*'s queue.

        Raises:
            SessionNotFoundError: session does not exist in the manager, or
                no queue has been registered for it.
            SessionDeadError: session status is DEAD.
            QueueFullError: the queue has reached QUEUE_MAX_SIZE.
        """
        session = self._manager.get_session(session_id)
        if session is None:
            raise SessionNotFoundError(f"Session not found: {session_id}")
        if session.status == SessionStatus.DEAD:
            raise SessionDeadError(f"Session is dead: {session_id}")

        queue = self._queues.get(session_id)
        if queue is None:
            raise SessionNotFoundError(f"No queue registered for session: {session_id}")

        if queue.full():
            raise QueueFullError(f"Queue full for session: {session_id}")

        await queue.put(command)

    def cleanup_session(self, session_id: str) -> None:
        """Cancel the consumer task and remove the queue for *session_id*.

        Safe to call for unknown session_ids.
        """
        consumer = self._consumers.pop(session_id, None)
        if consumer is not None:
            consumer.cancel()

        queue = self._queues.pop(session_id, None)
        if queue is not None:
            # Drain remaining items so nothing leaks.
            while not queue.empty():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

    async def shutdown(self) -> None:
        """Cancel all consumer tasks and clear internal state."""
        for consumer in list(self._consumers.values()):
            consumer.cancel()
        self._consumers.clear()
        self._queues.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _consume(self, session_id: str) -> None:
        """Long-running consumer: dequeues commands and sends them to the session."""
        queue = self._queues.get(session_id)
        if queue is None:
            return

        while True:
            try:
                command = await queue.get()
                try:
                    await self._manager.send_command(session_id, command)
                except Exception as exc:
                    logger.warning(
                        "send_command failed for session %s: %s",
                        session_id,
                        exc,
                    )
                finally:
                    queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(
                    "Unexpected error in consumer for session %s: %s",
                    session_id,
                    exc,
                )
                # Backoff to prevent tight loop on persistent errors
                await asyncio.sleep(1.0)
