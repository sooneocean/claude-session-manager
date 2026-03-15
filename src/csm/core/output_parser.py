"""JSON line parser for claude CLI stream-json output - T6"""
import json
import re
from dataclasses import dataclass
from enum import Enum


class EventType(Enum):
    INIT = "init"
    ASSISTANT = "assistant"
    RESULT = "result"
    TOOL_USE = "tool_use"
    RATE_LIMIT = "rate_limit"
    SYSTEM = "system"
    UNKNOWN = "unknown"


@dataclass
class ParsedEvent:
    event_type: EventType
    session_id: str | None = None
    # Result fields
    cost_usd: float | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    result_text: str | None = None
    # Assistant fields
    content_text: str | None = None
    # Init fields
    model: str | None = None
    # SOP detection
    sop_stage: str | None = None  # S0-S7 if detected in text
    # Raw data
    raw: dict | None = None


class OutputParser:
    """Parses JSON lines from claude CLI stream-json output."""

    def parse_line(self, line: str) -> ParsedEvent | None:
        """Parse a single JSON line from stream-json output.
        Returns ParsedEvent or None if line is empty/unparseable."""
        line = line.strip()
        if not line:
            return None
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return None

        event_type_str = data.get("type", "")
        session_id = data.get("session_id")

        if event_type_str == "result":
            return self._parse_result(data, session_id)
        elif event_type_str == "assistant":
            return self._parse_assistant(data, session_id)
        elif event_type_str == "system":
            subtype = data.get("subtype", "")
            if subtype == "init":
                return self._parse_init(data, session_id)
            return ParsedEvent(event_type=EventType.SYSTEM, session_id=session_id, raw=data)
        elif event_type_str == "rate_limit_event":
            return ParsedEvent(event_type=EventType.RATE_LIMIT, session_id=session_id, raw=data)
        else:
            return ParsedEvent(event_type=EventType.UNKNOWN, session_id=session_id, raw=data)

    def _parse_result(self, data: dict, session_id: str | None) -> ParsedEvent:
        usage = data.get("usage", {})
        result_text = data.get("result", "")
        sop_stage = self._detect_sop_stage(result_text)
        return ParsedEvent(
            event_type=EventType.RESULT,
            session_id=session_id,
            cost_usd=data.get("total_cost_usd"),
            tokens_in=usage.get("input_tokens"),
            tokens_out=usage.get("output_tokens"),
            result_text=result_text,
            sop_stage=sop_stage,
        )

    def _parse_assistant(self, data: dict, session_id: str | None) -> ParsedEvent:
        msg = data.get("message", {})
        content_parts = msg.get("content", [])
        text_parts = [p.get("text", "") for p in content_parts if p.get("type") == "text"]
        content_text = "\n".join(text_parts)
        sop_stage = self._detect_sop_stage(content_text)
        return ParsedEvent(
            event_type=EventType.ASSISTANT,
            session_id=session_id,
            content_text=content_text,
            sop_stage=sop_stage,
        )

    def _parse_init(self, data: dict, session_id: str | None) -> ParsedEvent:
        return ParsedEvent(
            event_type=EventType.INIT,
            session_id=session_id,
            model=data.get("model"),
            raw=data,
        )

    def _detect_sop_stage(self, text: str) -> str | None:
        """Detect SOP stage (S0-S7) from text content."""
        if not text:
            return None
        patterns = [
            r'Launching skill: s([0-7])',
            r'\bS([0-7])\b.*(?:需求|分析|審查|計畫|實作|Review|測試|提交)',
            r'(?:進入|啟動|開始)\s*S([0-7])',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return f"S{match.group(1)}"
        return None
