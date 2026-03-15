"""Tests for OutputParser (JSON line parser) - T6"""
import json
import pytest
from csm.core.output_parser import OutputParser, ParsedEvent, EventType


@pytest.fixture
def parser():
    return OutputParser()


class TestParseEdgeCases:

    def test_parse_empty_line(self, parser):
        assert parser.parse_line("") is None

    def test_parse_whitespace_only_line(self, parser):
        assert parser.parse_line("   \n") is None

    def test_parse_invalid_json(self, parser):
        assert parser.parse_line("not json at all") is None

    def test_parse_incomplete_json(self, parser):
        assert parser.parse_line('{"type": "result"') is None


class TestParseResultEvent:

    def test_parse_result_event(self, parser):
        data = {
            "type": "result",
            "session_id": "sess-abc",
            "total_cost_usd": 0.0123,
            "result": "Task completed successfully.",
            "usage": {
                "input_tokens": 500,
                "output_tokens": 200,
            },
        }
        event = parser.parse_line(json.dumps(data))
        assert event is not None
        assert event.event_type == EventType.RESULT
        assert event.session_id == "sess-abc"
        assert event.cost_usd == pytest.approx(0.0123)
        assert event.tokens_in == 500
        assert event.tokens_out == 200
        assert event.result_text == "Task completed successfully."

    def test_parse_result_event_missing_usage(self, parser):
        data = {
            "type": "result",
            "session_id": "sess-xyz",
            "total_cost_usd": 0.005,
            "result": "Done.",
        }
        event = parser.parse_line(json.dumps(data))
        assert event is not None
        assert event.event_type == EventType.RESULT
        assert event.tokens_in is None
        assert event.tokens_out is None
        assert event.cost_usd == pytest.approx(0.005)


class TestParseAssistantEvent:

    def test_parse_assistant_event(self, parser):
        data = {
            "type": "assistant",
            "session_id": "sess-def",
            "message": {
                "content": [
                    {"type": "text", "text": "Hello there!"},
                    {"type": "text", "text": "How can I help?"},
                ]
            },
        }
        event = parser.parse_line(json.dumps(data))
        assert event is not None
        assert event.event_type == EventType.ASSISTANT
        assert event.session_id == "sess-def"
        assert event.content_text == "Hello there!\nHow can I help?"

    def test_parse_assistant_event_filters_non_text_content(self, parser):
        data = {
            "type": "assistant",
            "session_id": "sess-ghi",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "bash", "input": {}},
                    {"type": "text", "text": "Running the command."},
                ]
            },
        }
        event = parser.parse_line(json.dumps(data))
        assert event is not None
        assert event.content_text == "Running the command."

    def test_parse_assistant_event_empty_content(self, parser):
        data = {
            "type": "assistant",
            "session_id": "sess-jkl",
            "message": {"content": []},
        }
        event = parser.parse_line(json.dumps(data))
        assert event is not None
        assert event.content_text == ""


class TestParseInitEvent:

    def test_parse_init_event(self, parser):
        data = {
            "type": "system",
            "subtype": "init",
            "session_id": "sess-init-001",
            "model": "claude-opus-4-5",
        }
        event = parser.parse_line(json.dumps(data))
        assert event is not None
        assert event.event_type == EventType.INIT
        assert event.session_id == "sess-init-001"
        assert event.model == "claude-opus-4-5"

    def test_parse_system_non_init(self, parser):
        data = {
            "type": "system",
            "subtype": "other",
            "session_id": "sess-sys",
        }
        event = parser.parse_line(json.dumps(data))
        assert event is not None
        assert event.event_type == EventType.SYSTEM
        assert event.session_id == "sess-sys"


class TestParseRateLimitEvent:

    def test_parse_rate_limit_event(self, parser):
        data = {
            "type": "rate_limit_event",
            "session_id": "sess-rl",
        }
        event = parser.parse_line(json.dumps(data))
        assert event is not None
        assert event.event_type == EventType.RATE_LIMIT
        assert event.session_id == "sess-rl"


class TestParseUnknownEvent:

    def test_parse_unknown_event(self, parser):
        data = {
            "type": "something_new",
            "session_id": "sess-unk",
        }
        event = parser.parse_line(json.dumps(data))
        assert event is not None
        assert event.event_type == EventType.UNKNOWN
        assert event.session_id == "sess-unk"
        assert event.raw == data


class TestSOPStageDetection:

    def test_parse_sop_stage_from_result(self, parser):
        data = {
            "type": "result",
            "session_id": "sess-sop",
            "result": "進入 S4 實作階段，開始撰寫程式碼。",
            "usage": {},
        }
        event = parser.parse_line(json.dumps(data))
        assert event is not None
        assert event.sop_stage == "S4"

    def test_parse_sop_stage_s0_from_result(self, parser):
        data = {
            "type": "result",
            "session_id": "sess-sop",
            "result": "S0 需求確認完成，進入下一階段。",
            "usage": {},
        }
        event = parser.parse_line(json.dumps(data))
        assert event is not None
        assert event.sop_stage == "S0"

    def test_parse_sop_stage_from_skill_launch(self, parser):
        data = {
            "type": "assistant",
            "session_id": "sess-skill",
            "message": {
                "content": [
                    {"type": "text", "text": "Launching skill: s4-implement for this task."},
                ]
            },
        }
        event = parser.parse_line(json.dumps(data))
        assert event is not None
        assert event.sop_stage == "S4"

    def test_no_sop_stage_when_absent(self, parser):
        data = {
            "type": "result",
            "session_id": "sess-nosop",
            "result": "Regular response without any SOP stage mention.",
            "usage": {},
        }
        event = parser.parse_line(json.dumps(data))
        assert event is not None
        assert event.sop_stage is None

    def test_sop_stage_from_start_pattern(self, parser):
        data = {
            "type": "assistant",
            "session_id": "sess-start",
            "message": {
                "content": [
                    {"type": "text", "text": "啟動 S1 分析中..."},
                ]
            },
        }
        event = parser.parse_line(json.dumps(data))
        assert event is not None
        assert event.sop_stage == "S1"
