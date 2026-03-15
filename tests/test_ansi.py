"""Tests for ANSI strip utility - T3"""
import pytest
from csm.utils.ansi import strip_ansi


class TestStripAnsi:

    def test_strip_sgr_color(self):
        # \x1b[31m = red color, \x1b[0m = reset
        text = "\x1b[31mhello\x1b[0m"
        assert strip_ansi(text) == "hello"

    def test_strip_sgr_reset(self):
        text = "\x1b[0m"
        assert strip_ansi(text) == ""

    def test_strip_csi_cursor(self):
        # CSI cursor movement sequences
        text = "\x1b[2J\x1b[Hclear screen"
        assert strip_ansi(text) == "clear screen"

    def test_strip_osc(self):
        # OSC sequence: \x1b]0;title\x07  or  \x1b]0;title\x1b\\
        text = "\x1b]0;window title\x07hello"
        assert strip_ansi(text) == "hello"

    def test_cr_overwrite(self):
        # \r causes cursor to return to start; last write wins
        text = "hello\rworld"
        assert strip_ansi(text) == "world"

    def test_cr_partial_overwrite(self):
        # "hello\rhi" -> "hillo" (hi overwrites first 2 chars of hello)
        text = "hello\rhi"
        assert strip_ansi(text) == "hillo"

    def test_plain_text_unchanged(self):
        text = "plain text with no escapes"
        assert strip_ansi(text) == "plain text with no escapes"

    def test_mixed_ansi_and_text(self):
        text = "\x1b[1mBold\x1b[0m and \x1b[32mgreen\x1b[0m"
        assert strip_ansi(text) == "Bold and green"
