"""ANSI escape sequence stripping utility."""
import re

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# CSI sequences: ESC [ ... (final byte in 0x40-0x7E range)
_CSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

# OSC sequences: ESC ] ... ST  (ST = BEL \x07 or ESC \)
_OSC_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")

# Any remaining lone ESC + single char (e.g. ESC c, ESC M, …)
_ESC_RE = re.compile(r"\x1b.")


def strip_ansi(text: str) -> str:
    """Remove ANSI/VT escape sequences from *text* and resolve CR overwrites.

    Processing order:
    1. Strip OSC sequences  (ESC ] ... BEL/ST)
    2. Strip CSI sequences  (ESC [ ... final-byte)
    3. Strip remaining lone ESC pairs
    4. Resolve CR (\\r) overwrites line-by-line
    """
    text = _OSC_RE.sub("", text)
    text = _CSI_RE.sub("", text)
    text = _ESC_RE.sub("", text)
    text = _resolve_cr(text)
    return text


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_cr(text: str) -> str:
    """Resolve carriage-return overwrites within each newline-delimited line."""
    lines = text.split("\n")
    resolved = [_resolve_cr_line(line) for line in lines]
    return "\n".join(resolved)


def _resolve_cr_line(line: str) -> str:
    """Simulate CR cursor-return within a single line.

    Each \\r resets the cursor to position 0; subsequent characters overwrite
    the existing content.  Example::

        "hello\\rworld"  -> "world"
        "hello\\rhi"     -> "hillo"
    """
    if "\r" not in line:
        return line

    buf = list(line)
    pos = 0
    result: list[str] = []

    i = 0
    while i < len(buf):
        ch = buf[i]
        if ch == "\r":
            pos = 0
        else:
            if pos < len(result):
                result[pos] = ch
            else:
                result.append(ch)
            pos += 1
        i += 1

    return "".join(result)
