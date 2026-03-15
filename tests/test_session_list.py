"""Tests for SessionList widget. T9"""
import pytest
from textual.app import App, ComposeResult

from csm.widgets.session_list import SessionList
from csm.models.session import SessionState, SessionConfig, SessionStatus


def _make_session(cwd: str = "/tmp/proj", status: SessionStatus = SessionStatus.WAIT) -> SessionState:
    s = SessionState.create(SessionConfig(cwd=cwd))
    s.status = status
    return s


class _SessionListApp(App):
    """Minimal host app for SessionList tests."""

    def compose(self) -> ComposeResult:
        yield SessionList(id="sl")

    def get_widget(self) -> SessionList:
        return self.query_one("#sl", SessionList)


# ---------------------------------------------------------------------------
# test_render_empty_list
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_render_empty_list():
    app = _SessionListApp()
    async with app.run_test() as pilot:
        sl = app.get_widget()
        sl.update_sessions([])
        await pilot.pause()
        assert sl.row_count == 0


# ---------------------------------------------------------------------------
# test_render_sessions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_render_sessions():
    sessions = [
        _make_session("/tmp/alpha", SessionStatus.RUN),
        _make_session("/tmp/beta", SessionStatus.WAIT),
    ]
    app = _SessionListApp()
    async with app.run_test() as pilot:
        sl = app.get_widget()
        sl.update_sessions(sessions)
        await pilot.pause()
        assert sl.row_count == 2


# ---------------------------------------------------------------------------
# test_add_session_row
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_session_row():
    app = _SessionListApp()
    async with app.run_test() as pilot:
        sl = app.get_widget()
        sl.update_sessions([])
        await pilot.pause()
        assert sl.row_count == 0

        sl.update_sessions([_make_session()])
        await pilot.pause()
        assert sl.row_count == 1


# ---------------------------------------------------------------------------
# test_remove_session_row
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_remove_session_row():
    sessions = [_make_session("/tmp/a"), _make_session("/tmp/b")]
    app = _SessionListApp()
    async with app.run_test() as pilot:
        sl = app.get_widget()
        sl.update_sessions(sessions)
        await pilot.pause()
        assert sl.row_count == 2

        # Remove one session
        sl.update_sessions(sessions[:1])
        await pilot.pause()
        assert sl.row_count == 1


# ---------------------------------------------------------------------------
# test_selection_change_event
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_selection_change_event():
    """Clicking a row should post SessionSelected with the correct session_id."""
    session = _make_session("/tmp/proj")

    received: list[SessionList.SessionSelected] = []

    class _CapturingApp(App):
        def compose(self) -> ComposeResult:
            yield SessionList(id="sl")

        def on_session_list_session_selected(self, event: SessionList.SessionSelected) -> None:
            received.append(event)

    app = _CapturingApp()
    async with app.run_test() as pilot:
        sl = app.query_one("#sl", SessionList)
        sl.update_sessions([session])
        await pilot.pause()
        # Move cursor to first row programmatically and trigger selection
        sl.move_cursor(row=0)
        sl.action_select_cursor()
        await pilot.pause()

        assert len(received) >= 1
        assert received[-1].session_id == session.session_id


# ---------------------------------------------------------------------------
# Sanity: STATUS_DISPLAY covers all statuses
# ---------------------------------------------------------------------------

def test_status_display_covers_all_statuses():
    for status in SessionStatus:
        assert status in SessionList.STATUS_DISPLAY
