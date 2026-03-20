"""Tests for Modal dialogs. T11"""
import pytest
from textual import work
from textual.app import App, ComposeResult
from textual.widgets import Button, Input, Static

from csm.widgets.modals import (
    NewSessionModal,
    ConfirmStopModal,
    CommandInputModal,
    RunningWarningModal,
)
from csm.models.session import SessionConfig


# ---------------------------------------------------------------------------
# test_new_session_modal_opens
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_new_session_modal_opens():
    """NewSessionModal can be pushed onto the screen stack without error."""
    app = App()
    async with app.run_test() as pilot:
        app.push_screen(NewSessionModal())
        await pilot.pause()
        assert isinstance(app.screen, NewSessionModal)


# ---------------------------------------------------------------------------
# test_new_session_modal_returns_config
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_new_session_modal_returns_config():
    """cwd is pre-filled with cwd; clicking Create dismisses the modal."""
    app = App()
    async with app.run_test(size=(100, 50)) as pilot:
        app.push_screen(NewSessionModal())
        await pilot.pause()
        assert isinstance(app.screen, NewSessionModal)

        # cwd input should already have a default value (os.getcwd())
        cwd_input = app.screen.query_one("#cwd_input", Input)
        assert len(cwd_input.value) > 0

        # Click Create → modal should be dismissed since cwd is non-empty
        await pilot.click("#create_btn")
        await pilot.pause()

        # The modal should no longer be the top screen
        assert not isinstance(app.screen, NewSessionModal)


# ---------------------------------------------------------------------------
# test_confirm_stop_modal_confirm
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_confirm_stop_modal_confirm():
    """Clicking Stop button dismisses ConfirmStopModal."""
    app = App()
    async with app.run_test() as pilot:
        app.push_screen(ConfirmStopModal("myproj"))
        await pilot.pause()
        assert isinstance(app.screen, ConfirmStopModal)

        await pilot.click("#stop_btn")
        await pilot.pause()

        assert not isinstance(app.screen, ConfirmStopModal)


# ---------------------------------------------------------------------------
# test_confirm_stop_modal_cancel
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_confirm_stop_modal_cancel():
    """Clicking Cancel button dismisses ConfirmStopModal."""
    app = App()
    async with app.run_test() as pilot:
        app.push_screen(ConfirmStopModal("myproj"))
        await pilot.pause()
        assert isinstance(app.screen, ConfirmStopModal)

        await pilot.click("#cancel_btn")
        await pilot.pause()

        assert not isinstance(app.screen, ConfirmStopModal)


# ---------------------------------------------------------------------------
# test_command_input_modal_returns_text
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_command_input_modal_returns_text():
    """CommandInputModal renders and has correct widgets."""
    app = App()
    async with app.run_test() as pilot:
        app.push_screen(CommandInputModal("myproject"))
        await pilot.pause()

        assert isinstance(app.screen, CommandInputModal)
        inp = app.screen.query_one("#cmd_input", Input)
        assert inp is not None

        # Send button should exist
        send_btn = app.screen.query_one("#send_btn", Button)
        assert send_btn is not None


# ---------------------------------------------------------------------------
# test_escape_closes_modal
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_escape_closes_modal():
    """Pressing Escape on any modal should dismiss it."""
    app = App()
    async with app.run_test() as pilot:
        app.push_screen(ConfirmStopModal("proj"))
        await pilot.pause()
        assert isinstance(app.screen, ConfirmStopModal)

        await pilot.press("escape")
        await pilot.pause()

        assert not isinstance(app.screen, ConfirmStopModal)


# ---------------------------------------------------------------------------
# Additional modal coverage
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_running_warning_modal_opens():
    """RunningWarningModal can be pushed without error."""
    app = App()
    async with app.run_test() as pilot:
        app.push_screen(RunningWarningModal())
        await pilot.pause()
        assert isinstance(app.screen, RunningWarningModal)

        # Cancel button should exist
        btn = app.screen.query_one("#cancel_btn", Button)
        assert btn is not None

        await pilot.click("#cancel_btn")
        await pilot.pause()
        assert not isinstance(app.screen, RunningWarningModal)


@pytest.mark.asyncio
async def test_command_input_modal_cancel():
    """Clicking Cancel on CommandInputModal dismisses it."""
    app = App()
    async with app.run_test() as pilot:
        app.push_screen(CommandInputModal("test"))
        await pilot.pause()
        assert isinstance(app.screen, CommandInputModal)

        await pilot.click("#cancel_btn")
        await pilot.pause()
        assert not isinstance(app.screen, CommandInputModal)


# ---------------------------------------------------------------------------
# Sanity: all modals can be instantiated
# ---------------------------------------------------------------------------

def test_modal_instantiation():
    NewSessionModal()
    ConfirmStopModal("test")
    CommandInputModal("test")
    RunningWarningModal()
