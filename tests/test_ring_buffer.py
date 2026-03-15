"""Tests for RingBuffer - T2"""
import pytest
from csm.utils.ring_buffer import RingBuffer


class TestRingBuffer:

    def test_append_within_capacity(self):
        buf = RingBuffer(maxlen=5)
        buf.append("line1")
        buf.append("line2")
        assert len(buf) == 2

    def test_append_exceeds_capacity(self):
        buf = RingBuffer(maxlen=3)
        for i in range(10):
            buf.append(f"line{i}")
        # Should only keep last 3
        assert len(buf) == 3
        lines = buf.get_lines()
        assert lines == ["line7", "line8", "line9"]

    def test_get_lines_all(self):
        buf = RingBuffer(maxlen=5)
        buf.append("a")
        buf.append("b")
        buf.append("c")
        assert buf.get_lines() == ["a", "b", "c"]

    def test_get_lines_limited(self):
        buf = RingBuffer(maxlen=10)
        for i in range(8):
            buf.append(f"line{i}")
        # get_lines(3) should return the last 3
        result = buf.get_lines(3)
        assert result == ["line5", "line6", "line7"]

    def test_empty_buffer(self):
        buf = RingBuffer()
        assert len(buf) == 0
        assert buf.get_lines() == []

    def test_clear(self):
        buf = RingBuffer(maxlen=5)
        buf.append("x")
        buf.append("y")
        buf.clear()
        assert len(buf) == 0
        assert buf.get_lines() == []

    def test_len(self):
        buf = RingBuffer(maxlen=10)
        assert len(buf) == 0
        buf.append("one")
        assert len(buf) == 1
        buf.append("two")
        assert len(buf) == 2

    def test_default_capacity(self):
        buf = RingBuffer()
        # Default maxlen should be 1000
        for i in range(1001):
            buf.append(f"line{i}")
        assert len(buf) == 1000
        # First line should be gone
        lines = buf.get_lines()
        assert lines[0] == "line1"
        assert lines[-1] == "line1000"
