"""RingBuffer - fixed-size circular buffer backed by collections.deque."""
from collections import deque
from typing import List


class RingBuffer:
    """Thread-unsafe fixed-capacity line buffer.

    Args:
        maxlen: Maximum number of lines to retain. Oldest lines are
                dropped silently when capacity is exceeded. Default 1000.
    """

    def __init__(self, maxlen: int = 1000) -> None:
        self._buf: deque[str] = deque(maxlen=maxlen)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append(self, line: str) -> None:
        """Append *line* to the buffer, evicting the oldest if full."""
        self._buf.append(line)

    def get_lines(self, n: int | None = None) -> List[str]:
        """Return up to *n* most-recent lines (all lines if *n* is None)."""
        if n is None:
            return list(self._buf)
        return list(self._buf)[-n:]

    def clear(self) -> None:
        """Remove all lines from the buffer."""
        self._buf.clear()

    def __len__(self) -> int:
        return len(self._buf)
