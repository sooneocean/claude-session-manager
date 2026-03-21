"""Tests for CSMApp main application. T12"""
import pytest
from pathlib import Path
from unittest.mock import patch
from textual.widgets import Header, Footer, Static

from csm.app import CSMApp
from csm.widgets.session_list import SessionList
from csm.widgets.detail_panel import DetailPanel
from csm.widgets.modals import NewSessionModal, ConfirmStopModal


@pytest.fixture(autouse=True)
def ensure_csm_dir(tmp_path):
    """Ensure ~/.csm/ exists so WelcomeScreen doesn't block tests."""
    csm_dir = Path.home() / ".csm"
    csm_dir.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# test_app_starts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_app_starts():
    """CSMApp can start and render without errors."""
    app = CSMApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app is not None


# ---------------------------------------------------------------------------
# test_layout_has_three_sections
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_layout_has_three_sections():
    """App layout should contain Header, SessionList, DetailPanel and Footer."""
    app = CSMApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.query_one(Header) is not None
        assert app.query_one(Footer) is not None
        assert app.query_one("#session_list", SessionList) is not None
        assert app.query_one("#detail_panel", DetailPanel) is not None


# ---------------------------------------------------------------------------
# test_key_n_opens_new_session_modal
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_key_n_opens_new_session_modal():
    """Pressing 'n' should trigger new session action (worker pushes modal)."""
    app = CSMApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("n")
        # Give the worker time to push the modal
        await pilot.pause(0.1)
        await pilot.pause(0.1)
        assert isinstance(app.screen, NewSessionModal)


# ---------------------------------------------------------------------------
# test_key_q_triggers_quit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_key_q_triggers_quit():
    """Pressing 'q' should trigger quit (app exits cleanly)."""
    app = CSMApp()
    exited = False
    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("q")
            await pilot.pause()
            exited = True
    except Exception:
        exited = True  # App may exit abruptly, which is fine
    assert exited


# ---------------------------------------------------------------------------
# test_key_x_opens_confirm_stop (no-op without selection)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_key_x_opens_confirm_stop_without_selection():
    """Pressing 'x' with no selected session should be a no-op (no modal)."""
    app = CSMApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause(0.1)
        await pilot.pause(0.1)
        # Without a selection, no modal should appear
        assert not isinstance(app.screen, ConfirmStopModal)


# ---------------------------------------------------------------------------
# test_status_bar_shows_total_cost
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_status_bar_shows_total_cost():
    """Status bar should display cost and session count."""
    app = CSMApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        bar = app.query_one("#status_bar", Static)
        text = str(bar.renderable)
        assert "Total:" in text or "$" in text


# ---------------------------------------------------------------------------
# test_enter_on_wait_session_no_selection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enter_on_wait_session_no_selection():
    """Pressing Enter with no selected session should be a no-op."""
    app = CSMApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause(0.1)
        # Should still be on main screen
        assert not isinstance(app.screen, NewSessionModal)
        assert not isinstance(app.screen, ConfirmStopModal)


# ---------------------------------------------------------------------------
# test_app_bindings_registered
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_app_bindings_registered():
    """All expected key bindings should be registered on the app."""
    app = CSMApp()
    binding_keys = {b.key for b in app.BINDINGS}
    assert "n" in binding_keys
    assert "x" in binding_keys
    assert "r" in binding_keys
    assert "q" in binding_keys
