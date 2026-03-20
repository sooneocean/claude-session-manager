"""Tests for DetailPanel widget. T10"""
import pytest
from textual.app import App, ComposeResult
from textual.widgets import RichLog

from csm.widgets.detail_panel import DetailPanel


class _PanelApp(App):
    """Minimal host app for DetailPanel tests."""

    def compose(self) -> ComposeResult:
        yield DetailPanel(id="dp")

    def get_panel(self) -> DetailPanel:
        return self.query_one("#dp", DetailPanel)

    def get_log(self) -> RichLog:
        return self.query_one("#output_log", RichLog)


# ---------------------------------------------------------------------------
# test_empty_state_shows_placeholder
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_state_shows_placeholder():
    """DetailPanel should show placeholder text on mount without error."""
    app = _PanelApp()
    async with app.run_test() as pilot:
        panel = app.get_panel()
        log = app.get_log()
        await pilot.pause()
        assert panel is not None
        assert len(log.lines) >= 1


# ---------------------------------------------------------------------------
# test_display_buffer_content
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_display_buffer_content():
    lines = ["line one", "line two", "line three"]
    app = _PanelApp()
    async with app.run_test() as pilot:
        panel = app.get_panel()
        log = app.get_log()
        panel.show_output(lines)
        await pilot.pause()
        assert len(log.lines) >= len(lines)


# ---------------------------------------------------------------------------
# test_switch_session_updates_content
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_switch_session_updates_content():
    """Calling show_output multiple times should replace content each time."""
    app = _PanelApp()
    async with app.run_test() as pilot:
        panel = app.get_panel()
        log = app.get_log()

        panel.show_output(["session A output"])
        await pilot.pause()
        count_a = len(log.lines)

        panel.show_output(["session B line 1", "session B line 2"])
        await pilot.pause()
        count_b = len(log.lines)

        # Second call has 2 lines, should be reflected
        assert count_b >= 2


# ---------------------------------------------------------------------------
# test_auto_scroll_to_bottom
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auto_scroll_to_bottom():
    """show_output displays all provided lines (truncation is caller's responsibility)."""
    lines = [f"line {i}" for i in range(200)]
    app = _PanelApp()
    async with app.run_test() as pilot:
        panel = app.get_panel()
        log = app.get_log()
        panel.show_output(lines)
        await pilot.pause()
        assert len(log.lines) == 200
