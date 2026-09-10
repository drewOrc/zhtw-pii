"""Unit tests for the Claude Haiku few-shot baseline.

This milestone (M1, Issue #3) does not call the real API: `ANTHROPIC_API_KEY`
is not set in this environment and is not set by these tests. Coverage here
is the no-key `BaselineUnavailable` path plus the JSON-parsing and
span-location logic, driven directly against `parse_response_text` and
`locate_spans` rather than a mocked SDK response object, so it does not
depend on the installed `anthropic` package's exact response object shape.
"""

import json

import pytest

from zhtw_pii.eval.baselines.claude_llm import (
    _FEW_SHOT_EXAMPLES,
    MAX_ENTITY_LENGTH,
    MODEL_ID,
    ClaudeLlmBaseline,
    ParsedItem,
    build_messages,
    locate_spans,
    parse_response_text,
)
from zhtw_pii.eval.types import BaselineUnavailable, Span

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


# --- parse_response_text: JSON body -> ParsedItem list -------------------


def test_parse_response_text_extracts_valid_items():
    raw_text = json.dumps({"spans": [{"text": "陳彥", "label": "PERSON"}]})
    items = parse_response_text(raw_text)
    assert items == [ParsedItem(text="陳彥", label="PERSON")]


def test_parse_response_text_drops_item_with_unrecognized_label():
    raw_text = json.dumps({"spans": [{"text": "陳彥", "label": "DATE"}]})
    assert parse_response_text(raw_text) == []


def test_parse_response_text_drops_item_missing_the_text_field_but_keeps_the_rest():
    raw_text = json.dumps(
        {
            "spans": [
                {"text": "陳彥", "label": "PERSON"},
                {"label": "ORG"},
            ]
        }
    )
    items = parse_response_text(raw_text)
    assert items == [ParsedItem(text="陳彥", label="PERSON")]


def test_parse_response_text_drops_item_that_is_not_a_json_object():
    raw_text = json.dumps({"spans": ["just a string, not an object"]})
    assert parse_response_text(raw_text) == []


def test_parse_response_text_handles_empty_spans_list():
    assert parse_response_text(json.dumps({"spans": []})) == []


def test_parse_response_text_raises_on_unparseable_json():
    """A malformed top-level response is a real failure, not a droppable item."""
    with pytest.raises(json.JSONDecodeError):
        parse_response_text("not valid json at all {{{")


def test_parse_response_text_preserves_the_models_reported_order():
    """locate_spans() depends on this order to advance its search cursor."""
    raw_text = json.dumps(
        {"spans": [{"text": "林小華", "label": "PERSON"}, {"text": "陳彥", "label": "PERSON"}]}
    )
    items = parse_response_text(raw_text)
    assert [item.text for item in items] == ["林小華", "陳彥"]


# --- locate_spans: ParsedItem list + source text -> Span list ------------


def test_locate_spans_finds_a_normal_surface_string():
    text = "客戶陳彥來電。"
    spans, counts = locate_spans(text, [ParsedItem(text="陳彥", label="PERSON")])
    assert len(spans) == 1
    span = spans[0]
    assert text[span.start : span.end] == "陳彥"
    assert span.label == "PERSON"
    assert counts == {"unlocated_spans": 0, "relocated_spans": 0, "ignored_items": 0}


def test_locate_spans_locates_full_width_text_with_honorific_suffix_exactly():
    text = "客戶陳彥先生來電，地址在台北市。"
    spans, counts = locate_spans(text, [ParsedItem(text="陳彥先生", label="PERSON")])
    assert len(spans) == 1
    span = spans[0]
    assert text[span.start : span.end] == "陳彥先生"
    assert counts["unlocated_spans"] == 0


def test_locate_spans_same_surface_string_appearing_twice_yields_two_distinct_spans():
    text = "陳彥今天來過，陳彥留下聯絡方式。"
    items = [ParsedItem(text="陳彥", label="PERSON"), ParsedItem(text="陳彥", label="PERSON")]
    spans, counts = locate_spans(text, items)
    assert len(spans) == 2
    assert spans[0].start < spans[1].start
    assert text[spans[0].start : spans[0].end] == "陳彥"
    assert text[spans[1].start : spans[1].end] == "陳彥"
    assert counts["relocated_spans"] == 0
    assert counts["unlocated_spans"] == 0


def test_locate_spans_item_not_found_anywhere_counts_as_unlocated():
    text = "本句沒有目標實體。"
    spans, counts = locate_spans(text, [ParsedItem(text="王小明", label="PERSON")])
    assert spans == []
    assert counts["unlocated_spans"] == 1
    assert counts["relocated_spans"] == 0


def test_locate_spans_falls_back_to_searching_from_the_start_when_out_of_order():
    """The second item's only occurrence sits before the first item's match,
    so it is not found from the advanced cursor and must be relocated from
    the start of the string. The two spans are still returned in text order.
    """
    text = "陳彥的鄰居是林小華。"
    items = [
        ParsedItem(text="林小華", label="PERSON"),
        ParsedItem(text="陳彥", label="PERSON"),
    ]
    spans, counts = locate_spans(text, items)
    assert len(spans) == 2
    assert spans[0].start == 0
    assert text[spans[0].start : spans[0].end] == "陳彥"
    assert text[spans[1].start : spans[1].end] == "林小華"
    assert counts["relocated_spans"] == 1
    assert counts["unlocated_spans"] == 0


def test_locate_spans_deduplicates_a_hallucinated_repeat_of_the_same_span():
    """Two items pointing at the same one-off entity must not double-count."""
    text = "陳彥報案。"
    items = [ParsedItem(text="陳彥", label="PERSON"), ParsedItem(text="陳彥", label="PERSON")]
    spans, counts = locate_spans(text, items)
    assert spans == [Span(start=0, end=2, label="PERSON")]
    assert counts["relocated_spans"] == 1


def test_locate_spans_ignores_empty_text_item():
    spans, counts = locate_spans("陳彥報案。", [ParsedItem(text="", label="PERSON")])
    assert spans == []
    assert counts == {"unlocated_spans": 0, "relocated_spans": 0, "ignored_items": 1}


def test_locate_spans_ignores_text_item_longer_than_max_entity_length():
    overlong = "陳" * (MAX_ENTITY_LENGTH + 1)
    spans, counts = locate_spans(overlong, [ParsedItem(text=overlong, label="PERSON")])
    assert spans == []
    assert counts["ignored_items"] == 1


def test_locate_spans_handles_no_items():
    spans, counts = locate_spans("陳彥報案。", [])
    assert spans == []
    assert counts == {"unlocated_spans": 0, "relocated_spans": 0, "ignored_items": 0}


# --- _parse_or_count_failure: response body -> ParsedItem list, never raises --


def test_parse_or_count_failure_absorbs_unparseable_json_as_no_items():
    """The `predict()` wrapper must not propagate a single bad response.

    `run_baseline()` treats any exception out of `predict()` as fatal for
    the entire 300-example run (see benchmark.py); one malformed response
    must not discard the other 299 examples' already-spent API cost.
    """
    baseline = ClaudeLlmBaseline()
    items = baseline._parse_or_count_failure("not valid json at all {{{")
    assert items == []


def test_parse_or_count_failure_increments_parse_failures_counter():
    baseline = ClaudeLlmBaseline()
    assert baseline.parse_failures == 0
    baseline._parse_or_count_failure("still not json [[[")
    assert baseline.parse_failures == 1


def test_parse_or_count_failure_accumulates_across_multiple_bad_responses():
    baseline = ClaudeLlmBaseline()
    baseline._parse_or_count_failure("bad {{{")
    baseline._parse_or_count_failure("also bad [[[")
    assert baseline.parse_failures == 2


def test_parse_or_count_failure_does_not_count_a_well_formed_response():
    baseline = ClaudeLlmBaseline()
    raw_text = json.dumps({"spans": [{"text": "陳彥", "label": "PERSON"}]})
    items = baseline._parse_or_count_failure(raw_text)
    assert items == [ParsedItem(text="陳彥", label="PERSON")]
    assert baseline.parse_failures == 0


# --- build_messages -------------------------------------------------------


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


def test_few_shot_examples_span_text_is_a_verbatim_substring_of_its_own_example():
    """Regression guard for the bug this baseline shipped with.

    The offset-based predecessor's `_FEW_SHOT_EXAMPLES` hardcoded a
    `start`/`end` pair for two spans that did not actually point at the
    entity they were meant to illustrate (an ADDRESS and a PERSON span
    both landed a few characters off), and nothing caught it because no
    test ever checked a few-shot example's own span against its text. The
    new `text`-based schema cannot silently drift the same way an integer
    offset could, but a hand-typed `text` field could still be a typo away
    from its example; this keeps that path checked.
    """
    for example in _FEW_SHOT_EXAMPLES:
        for span in example["spans"]:
            assert span["text"] in example["text"]
