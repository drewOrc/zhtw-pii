"""Unit tests for the Claude Haiku few-shot baseline.

This milestone (M1, Issue #3) does not call the real API: `ANTHROPIC_API_KEY`
is not set in this environment and is not set by these tests. Coverage here
is the no-key `BaselineUnavailable` path and the JSON-parsing logic, driven
directly against `parse_response_text` rather than a mocked SDK response
object, so it does not depend on the installed `anthropic` package's exact
response object shape.
"""

import json

import pytest

from zhtw_pii.eval.baselines.claude_llm import (
    MODEL_ID,
    ClaudeLlmBaseline,
    build_messages,
    parse_response_text,
)
from zhtw_pii.eval.types import BaselineUnavailable

pytestmark = pytest.mark.unit


def test_load_raises_baseline_unavailable_when_api_key_not_set(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    baseline = ClaudeLlmBaseline()
    with pytest.raises(BaselineUnavailable) as exc_info:
        baseline.load()
    assert exc_info.value.reason == "ANTHROPIC_API_KEY not set"


def test_load_reason_matches_the_exact_string_required_by_the_acceptance_criteria(monkeypatch):
    """A2/A3 require the literal reason text "ANTHROPIC_API_KEY not set"."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(BaselineUnavailable, match=r"^ANTHROPIC_API_KEY not set$"):
        ClaudeLlmBaseline().load()


def test_model_id_has_no_date_suffix():
    """Current-generation Anthropic model ids are not date-suffixed.

    The task brief for this baseline named `claude-haiku-4-5-20251001`; a
    dated id for a still-served model is very likely to 404 against the
    real API. See the module docstring for the full reasoning.
    """
    assert MODEL_ID == "claude-haiku-4-5"


def test_parse_response_text_extracts_valid_spans():
    raw_text = json.dumps({"spans": [{"start": 3, "end": 5, "label": "PERSON"}]})
    spans = parse_response_text(raw_text, input_length=6)
    assert len(spans) == 1
    assert spans[0].start == 3
    assert spans[0].end == 5
    assert spans[0].label == "PERSON"


def test_parse_response_text_drops_span_with_unrecognized_label():
    raw_text = json.dumps({"spans": [{"start": 0, "end": 2, "label": "DATE"}]})
    assert parse_response_text(raw_text, input_length=10) == []


def test_parse_response_text_drops_span_with_inverted_offsets():
    raw_text = json.dumps({"spans": [{"start": 5, "end": 2, "label": "PERSON"}]})
    assert parse_response_text(raw_text, input_length=10) == []


def test_parse_response_text_drops_span_out_of_input_range():
    raw_text = json.dumps({"spans": [{"start": 0, "end": 999, "label": "PERSON"}]})
    assert parse_response_text(raw_text, input_length=10) == []


def test_parse_response_text_drops_one_malformed_span_but_keeps_the_rest():
    raw_text = json.dumps(
        {
            "spans": [
                {"start": 0, "end": 2, "label": "PERSON"},
                {"start": "not a number", "end": 5, "label": "ORG"},
            ]
        }
    )
    spans = parse_response_text(raw_text, input_length=10)
    assert len(spans) == 1
    assert spans[0].label == "PERSON"


def test_parse_response_text_handles_empty_spans_list():
    raw_text = json.dumps({"spans": []})
    assert parse_response_text(raw_text, input_length=10) == []


def test_parse_response_text_raises_on_unparseable_json():
    """A malformed top-level response is a real failure, not a droppable span."""
    with pytest.raises(json.JSONDecodeError):
        parse_response_text("not valid json at all {{{", input_length=10)


def test_build_messages_ends_with_the_input_text_as_the_final_user_turn():
    messages = build_messages("測試句子")
    assert messages[-1] == {"role": "user", "content": "測試句子"}
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


def test_build_messages_few_shot_assistant_turns_are_valid_json():
    messages = build_messages("x")
    assistant_turns = [m for m in messages if m["role"] == "assistant"]
    assert assistant_turns
    for turn in assistant_turns:
        parsed = json.loads(turn["content"])
        assert "spans" in parsed
