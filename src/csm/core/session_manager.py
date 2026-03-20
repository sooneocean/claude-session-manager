"""SessionManager - manages Claude CLI sessions via --print --resume mode. T7"""
import asyncio
import os
from datetime import datetime

from csm.models.session import SessionState, SessionConfig, SessionStatus
from csm.models.cost import CostAggregator
from csm.core.output_parser import OutputParser, EventType, ResultEvent, AssistantEvent
from csm.utils.ring_buffer import RingBuffer


class DirectoryNotFoundError(Exception):
    """Raised when the configured working directory does not exist."""


class DuplicateSessionError(Exception):
    """Raised when a session with the same cwd+resume_id already exists."""


class SessionNotFoundError(Exception):
    """Raised when referencing a session_id that does not exist."""


class OutputBufferStore:
    """Manages per-session RingBuffer output buffers."""

    def __init__(self) -> None:
        self._buffers: dict[str, RingBuffer] = {}

    def create(self, session_id: str, capacity: int = 1000) -> RingBuffer:
        buf = RingBuffer(capacity)
        self._buffers[session_id] = buf
        return buf

    def get(self, session_id: str) -> RingBuffer | None:
        return self._buffers.get(session_id)

    def remove(self, session_id: str) -> None:
        self._buffers.pop(session_id, None)


class SessionManager:
    """Manages Claude Code sessions using --print --resume mode.

    Each interaction is an independent ``claude -p --resume SESSION_ID``
    invocation.  The manager tracks state, cost and buffered output across
    calls.
    """

    SESSION_LIMIT = 20
    AUTO_COMPACT_TOKEN_THRESHOLD = 50000  # tokens_in + tokens_out

    def __init__(self, session_limit: int | None = None,
                 auto_compact_threshold: int | None = None,
                 buffer_capacity: int | None = None) -> None:
        if session_limit is not None:
            self.SESSION_LIMIT = session_limit
        if auto_compact_threshold is not None:
            self.AUTO_COMPACT_TOKEN_THRESHOLD = auto_compact_threshold
        self._buffer_capacity = buffer_capacity or 1000
        self._sessions: dict[str, SessionState] = {}
        self._parser = OutputParser()
        self._cost_aggregator = CostAggregator()
        self._buffer_store = OutputBufferStore()
        # Maps session_id → currently-executing subprocess (short-lived).
        self._running_processes: dict[str, asyncio.subprocess.Process] = {}
        self._background_tasks: dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def cost_aggregator(self) -> CostAggregator:
        return self._cost_aggregator

    @property
    def buffer_store(self) -> OutputBufferStore:
        return self._buffer_store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def spawn(self, config: SessionConfig) -> str:
        """Start a new Claude CLI session.

        Returns the internal session_id (UUID).

        Raises:
            DirectoryNotFoundError: cwd does not exist.
            DuplicateSessionError: an active session with the same
                cwd+resume_id already exists.
            RuntimeError: SESSION_LIMIT exceeded.
        """
        # Normalize path: expand ~ and resolve relative paths
        config = SessionConfig(
            cwd=os.path.abspath(os.path.expanduser(config.cwd)),
            resume_id=config.resume_id,
            model=config.model,
            permission_mode=config.permission_mode,
            name=config.name,
            max_budget_usd=config.max_budget_usd,
        )
        if not os.path.isdir(config.cwd):
            raise DirectoryNotFoundError(f"Directory not found: {config.cwd}")

        # Check for duplicate active session
        for s in self._sessions.values():
            if (
                s.config.cwd == config.cwd
                and s.config.resume_id == config.resume_id
                and s.status not in (SessionStatus.DONE, SessionStatus.DEAD)
            ):
                raise DuplicateSessionError(
                    f"Active session already exists for cwd={config.cwd!r} "
                    f"resume_id={config.resume_id!r}"
                )

        # Enforce session limit
        active = sum(
            1
            for s in self._sessions.values()
            if s.status not in (SessionStatus.DONE, SessionStatus.DEAD)
        )
        if active >= self.SESSION_LIMIT:
            raise RuntimeError(
                f"Session limit ({self.SESSION_LIMIT}) reached"
            )

        state = SessionState.create(config)
        self._sessions[state.session_id] = state
        self._buffer_store.create(state.session_id, self._buffer_capacity)

        initial_prompt = "continue" if config.resume_id else "hello, ready to work"

        state.status = SessionStatus.RUN

        # Run initial claude call in background task (non-blocking)
        async def _background_spawn():
            try:
                result = await self._run_claude(state, initial_prompt)
                if result is not None:
                    state.status = SessionStatus.WAIT
                else:
                    result = await self._run_claude(state, initial_prompt)
                    state.status = SessionStatus.WAIT if result is not None else SessionStatus.DEAD
            except Exception:
                state.status = SessionStatus.DEAD

        import asyncio
        self._background_tasks[state.session_id] = asyncio.create_task(_background_spawn())

        return state.session_id

    async def send_command(self, session_id: str, command: str) -> None:
        """Send *command* to *session_id*. Runs in background (non-blocking).

        Raises:
            SessionNotFoundError: session does not exist.
            RuntimeError: session is DEAD.
        """
        state = self._sessions.get(session_id)
        if not state:
            raise SessionNotFoundError(f"Session not found: {session_id}")

        if state.status == SessionStatus.DEAD:
            raise RuntimeError("Cannot send command to DEAD session")

        state.status = SessionStatus.RUN

        async def _background_command():
            try:
                result = await self._run_claude(state, command)
                if result is not None:
                    state.status = SessionStatus.WAIT
                    await self._auto_compact_if_needed(state)
                else:
                    result = await self._run_claude(state, command)
                    state.status = SessionStatus.WAIT if result is not None else SessionStatus.DEAD
            except Exception:
                state.status = SessionStatus.DEAD

        import asyncio
        self._background_tasks[session_id] = asyncio.create_task(_background_command())

    async def _auto_compact_if_needed(self, state: SessionState) -> None:
        """Send /compact if session token usage exceeds threshold."""
        total_tokens = state.tokens_in + state.tokens_out
        if total_tokens < self.AUTO_COMPACT_TOKEN_THRESHOLD:
            return
        if not state.claude_session_id:
            return
        # Only compact if not already a /compact command (prevent infinite loop)
        if state.last_result and "/compact" in state.last_result:
            return
        import logging
        logging.getLogger(__name__).info(
            "Auto-compact triggered for session %s (tokens: %d)",
            state.session_id, total_tokens,
        )
        state.status = SessionStatus.RUN
        await self._run_claude(state, "/compact")
        state.status = SessionStatus.WAIT
        # Reset token counters after compact
        state.tokens_in = 0
        state.tokens_out = 0
        self._cost_aggregator.update(state.session_id, 0, 0, state.cost_usd)

    async def stop(self, session_id: str) -> None:
        """Mark *session_id* as DONE.  Terminates any in-flight process."""
        state = self._sessions.get(session_id)
        if not state:
            raise SessionNotFoundError(f"Session not found: {session_id}")

        proc = self._running_processes.pop(session_id, None)
        if proc is not None and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()

        state.status = SessionStatus.DONE


    async def restart(self, session_id: str) -> str:
        """Restart *session_id* with its original config.  Returns new session_id."""
        state = self._sessions.get(session_id)
        if not state:
            raise SessionNotFoundError(f"Session not found: {session_id}")

        config = state.config
        await self.remove(session_id)
        return await self.spawn(config)

    async def remove(self, session_id: str) -> None:
        """Remove a session completely (no DONE status update)."""
        proc = self._running_processes.pop(session_id, None)
        if proc is not None and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        self._sessions.pop(session_id, None)
        self._cost_aggregator.remove(session_id)
        self._buffer_store.remove(session_id)

    def get_sessions(self) -> list[SessionState]:
        return list(self._sessions.values())

    def get_session(self, session_id: str) -> SessionState | None:
        return self._sessions.get(session_id)

    async def flush(self) -> None:
        """Await all pending background tasks. Useful for testing."""
        tasks = list(self._background_tasks.values())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._background_tasks.clear()

    async def shutdown(self) -> None:
        """Gracefully stop all sessions."""
        await self.flush()
        for sid in list(self._sessions.keys()):
            try:
                await self.stop(sid)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run_claude(self, state: SessionState, prompt: str) -> str | None:
        """Execute a single ``claude -p`` call and process stream-JSON output.

        Returns the result text on success, None on non-zero exit.
        """
        cmd = ["claude", "-p", "--output-format", "stream-json", "--verbose",
               "--include-partial-messages"]

        # Prefer the runtime session id obtained from a previous call; fall
        # back to the config-level resume_id for the very first call.
        if state.claude_session_id:
            cmd.extend(["--resume", state.claude_session_id])
        elif state.config.resume_id:
            cmd.extend(["--resume", state.config.resume_id])

        if state.config.model:
            cmd.extend(["--model", state.config.model])

        if state.config.max_budget_usd is not None:
            cmd.extend(["--max-budget-usd", str(state.config.max_budget_usd)])

        if state.config.name:
            cmd.extend(["--name", state.config.name])

        cmd.append(prompt)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=state.config.cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._running_processes[state.session_id] = proc

        # Stream stdout line-by-line for real-time updates
        result_text: str | None = None
        buf = self._buffer_store.get(state.session_id)

        try:
            while True:
                try:
                    raw_line = await asyncio.wait_for(
                        proc.stdout.readline(), timeout=600
                    )
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    state.status = SessionStatus.DEAD
                    return None

                if not raw_line:  # EOF — process finished
                    break

                line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
                event = self._parser.parse_line(line)
                if not event:
                    continue

                state.last_activity = datetime.now()

                # Capture the CLI session_id on first occurrence.
                if event.session_id and not state.claude_session_id:
                    state.claude_session_id = event.session_id

                if isinstance(event, ResultEvent):
                    result_text = event.result_text or ""
                    if event.cost_usd is not None:
                        state.cost_usd = event.cost_usd
                    if event.tokens_in is not None:
                        state.tokens_in += event.tokens_in
                    if event.tokens_out is not None:
                        state.tokens_out += event.tokens_out
                    self._cost_aggregator.update(
                        state.session_id,
                        state.tokens_in,
                        state.tokens_out,
                        state.cost_usd,
                    )
                    if buf is not None and result_text:
                        for rl in result_text.split("\n"):
                            buf.append(rl)

                elif isinstance(event, AssistantEvent) and event.content_text and buf is not None:
                    for rl in event.content_text.split("\n"):
                        buf.append(rl)

                if event.sop_stage:
                    state.sop_stage = event.sop_stage

        finally:
            self._running_processes.pop(state.session_id, None)

        # Wait for process to fully exit
        await proc.wait()
        state.exit_code = proc.returncode
        state.last_result = result_text or ""

        if proc.returncode != 0:
            state.status = SessionStatus.DEAD
            return None

        return result_text
