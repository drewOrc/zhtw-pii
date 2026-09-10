"""Claude Haiku few-shot baseline: the accuracy/cost/privacy reference point.

Requires `ANTHROPIC_API_KEY`. Without it, `load()` raises
`BaselineUnavailable("ANTHROPIC_API_KEY not set")` and the runner writes
an "unevaluated" result. The test suite exercises only that no-key path
plus the JSON-parsing and span-location logic directly, never a real API
call; see tests/test_eval_llm_baseline.py.

Model id: the task brief for this baseline named
`claude-haiku-4-5-20251001`. Current Anthropic model ids for models still
being served do not carry a date suffix; the live-served id is
`claude-haiku-4-5`, used here instead, and it resolved on the first real
run made with a key, no date-suffixed fallback needed (see
`results/benchmark/v0/llm.json`'s `metadata.model_id`). `MODEL_ID` is a
module constant so pointing this at a different id is a one-line change.

`predict()` uses `output_config: {"format": {"type": "json_schema", ...}}`
(structured outputs) rather than prompting for JSON and hoping, so a
malformed top-level response is a genuine API-contract violation, not a
prompting failure; `_parse_or_count_failure()` absorbs one anyway rather
than failing the whole 300-example run over it (see that method's
docstring).

Span location: the model is not asked for character offsets. The first
run that was (schema `{start, end, label}`, an offset pair into the
original string) scored 439 spans overlap-matched against gold but only
179 of those exact-matched: the model found the right entities but
miscounted where they sat, with the predicted start shifted anywhere from
-6 to +3 characters off the true one depending on the example. Asking an
LLM to count characters is unreliable in a way asking it to copy text is
not, so the schema now asks for the literal entity substring
(`{text, label}`) and `locate_spans()` finds each returned string in the
original input itself with `str.find`, deterministically, instead of
trusting a model-reported index.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    # Only for type checking: keeps this a static-analysis-only import, so
    # `anthropic` is never actually imported unless load() runs (and load()
    # itself already imports it lazily, guarded by BaselineUnavailable).
    # anthropic is an optional dependency (the `benchmark` group), not
    # installed for CI's lint job; pyright cannot resolve it there either.
    import anthropic  # pyright: ignore[reportMissingImports]

from zhtw_pii.eval.types import BaselineMetadata, BaselineUnavailable, Span

MODEL_ID = "claude-haiku-4-5"
MAX_TOKENS = 4096
LABELS: tuple[str, ...] = ("PERSON", "ADDRESS", "ORG")

# Above this many characters, a returned "entity" is not a name, address
# fragment, or org this project's label set covers; treated as a
# hallucinated near-duplicate of the whole input rather than searched for.
MAX_ENTITY_LENGTH = 100

SYSTEM_PROMPT = (
    "You detect Traditional Chinese PERSON names, ADDRESS fragments, and "
    "ORG (organization) names in short input sentences. Copy each entity "
    "verbatim as it appears in the input, including full-width characters "
    "and honorific suffixes exactly as written; do not normalize or "
    "translate it. Only use the labels PERSON, ADDRESS, ORG. If there are "
    "no matching entities, return an empty list. Never include a span for "
    "a number, date, amount, or reference code."
)

# The ADDRESS span in example 2 and the PERSON span in example 3 below are
# the correct entity text. The previous offset-based schema's hardcoded
# start/end for both had drifted a few characters off the actual entity
# ("址為台北市中正區忠孝路2段4" and "為林小" respectively) without any test
# catching it, since nothing checked a few-shot example's own span against
# its text. A second, independent data point for why hand-maintained
# character offsets are fragile even when a human wrote them, not just
# when a model reports them.
_FEW_SHOT_EXAMPLES: tuple[dict[str, Any], ...] = (
    {
        "text": "姓名：陳彥。",
        "spans": [{"text": "陳彥", "label": "PERSON"}],
    },
    {
        "text": "客戶王小明來電反映，居住地址為台北市中正區忠孝路2段45號。",
        "spans": [
            {"text": "王小明", "label": "PERSON"},
            {"text": "台北市中正區忠孝路2段45號", "label": "ADDRESS"},
        ],
    },
    {
        "text": "本案由誠信協會承辦，聯絡人為林小華。",
        "spans": [
            {"text": "誠信協會", "label": "ORG"},
            {"text": "林小華", "label": "PERSON"},
        ],
    },
    {
        "text": "訂單編號A12345已出貨，預計2025年01月01日送達，金額NT$500。",
        "spans": [],
    },
)

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "spans": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "label": {"type": "string", "enum": list(LABELS)},
                },
                "required": ["text", "label"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["spans"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ParsedItem:
    """One model-reported entity, before its text has been located in the input."""

    text: str
    label: str


def build_messages(text: str) -> list[dict[str, Any]]:
    """Build the few-shot message history ending in the example to label."""
    messages: list[dict[str, Any]] = []
    for example in _FEW_SHOT_EXAMPLES:
        messages.append({"role": "user", "content": example["text"]})
        messages.append(
            {
                "role": "assistant",
                "content": json.dumps({"spans": example["spans"]}, ensure_ascii=False),
            }
        )
    messages.append({"role": "user", "content": text})
    return messages


def parse_response_text(raw_text: str) -> list[ParsedItem]:
    """Parse one JSON response body into validated (text, label) items.

    An item with a missing `text`/`label` field, a non-string value for
    either, or an unrecognized label is dropped rather than raised on: one
    bad item from the model should not fail the whole example. Items are
    returned in the model's reported order, since `locate_spans()` depends
    on that order to advance its search cursor through the input. An
    unparseable top-level body does raise (`json.JSONDecodeError`), since
    that means the response is not usable at all and the caller should
    surface it as a real failure.
    """
    data = json.loads(raw_text)
    items: list[ParsedItem] = []
    for raw_span in data.get("spans", []):
        try:
            text = str(raw_span["text"])
            label = str(raw_span["label"])
        except (KeyError, TypeError):
            continue
        if label not in LABELS:
            continue
        items.append(ParsedItem(text=text, label=label))
    return items


def locate_spans(text: str, items: Sequence[ParsedItem]) -> tuple[list[Span], dict[str, int]]:
    """Find each parsed item's text in `text` and turn it into a `Span`.

    Items are walked in the model's reported order, advancing a `cursor`
    to the end of the previous successfully located match before searching
    for the next one. This lets the same surface string appearing twice in
    the input (a name mentioned once and then referred to again) resolve
    to two distinct spans instead of the same one twice.

    An item not found from `cursor` onward is searched again from the
    start of the string, counted in `relocated_spans` when that recovers
    it. Still not found, it is dropped rather than guessing a position,
    counted in `unlocated_spans`. An empty string, or one longer than
    `MAX_ENTITY_LENGTH` characters, is dropped before any search is
    attempted, counted in `ignored_items`: an empty string would otherwise
    "match" at the cursor position itself, and this project's entities are
    never anywhere near 100 characters long.

    Returns the located spans, deduplicated and sorted by
    `(start, end, label)`, plus the three counts above (each a plain
    dict key rather than a dataclass, since this is consumed once by
    `predict()` to add onto the running per-baseline totals and nowhere
    else).
    """
    spans: list[Span] = []
    cursor = 0
    unlocated_spans = 0
    relocated_spans = 0
    ignored_items = 0
    for item in items:
        surface = item.text
        if not surface or len(surface) > MAX_ENTITY_LENGTH:
            ignored_items += 1
            continue
        start = text.find(surface, cursor)
        if start == -1:
            start = text.find(surface, 0)
            if start == -1:
                unlocated_spans += 1
                continue
            relocated_spans += 1
        end = start + len(surface)
        spans.append(Span(start=start, end=end, label=item.label))
        cursor = end
    unique_spans = sorted(set(spans), key=lambda span: (span.start, span.end, span.label))
    return unique_spans, {
        "unlocated_spans": unlocated_spans,
        "relocated_spans": relocated_spans,
        "ignored_items": ignored_items,
    }


class ClaudeLlmBaseline:
    """Few-shot Claude Haiku baseline; requires `ANTHROPIC_API_KEY`."""

    name = "llm"
    label_mapping = {"PERSON": "PERSON", "ADDRESS": "ADDRESS", "ORG": "ORG"}
    params: dict[str, object] = {
        "model": MODEL_ID,
        "max_tokens": MAX_TOKENS,
        "few_shot_examples": len(_FEW_SHOT_EXAMPLES),
        "structured_output": "json_schema",
    }
    # Surfaced into the result JSON's metadata.span_location by benchmark.py,
    # the same getattr-based convention parse_failures/bytes_sent_total use.
    span_location = "surface-text"

    def __init__(self) -> None:
        self._client: anthropic.Anthropic | None = None
        self.bytes_sent_total = 0
        self.parse_failures = 0
        self.unlocated_spans = 0
        self.relocated_spans = 0
        self.ignored_items = 0

    def load(self) -> BaselineMetadata:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise BaselineUnavailable("ANTHROPIC_API_KEY not set")
        try:
            import anthropic  # pyright: ignore[reportMissingImports]
        except ImportError as exc:
            raise BaselineUnavailable(f"anthropic package not installed: {exc}") from exc
        try:
            self._client = anthropic.Anthropic(api_key=api_key)
        except Exception as exc:  # noqa: BLE001 - any setup failure means unevaluated
            raise BaselineUnavailable(f"failed to construct Anthropic client: {exc}") from exc
        return BaselineMetadata(
            model_id=MODEL_ID,
            model_version=MODEL_ID,
            size_mb=None,
            data_leaves_machine=True,
            bytes_sent=0,
            package_versions={"anthropic": getattr(anthropic, "__version__", "unknown")},
        )

    def predict(self, text: str) -> list[Span]:
        if self._client is None:
            raise RuntimeError("ClaudeLlmBaseline.predict called before load()")
        messages = build_messages(text)
        prompt_bytes = len(SYSTEM_PROMPT.encode("utf-8")) + sum(
            len(str(message["content"]).encode("utf-8")) for message in messages
        )
        self.bytes_sent_total += prompt_bytes
        response = self._client.messages.create(
            model=MODEL_ID,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            # build_messages() returns plain dicts matching the SDK's
            # MessageParam shape; cast rather than import anthropic.types
            # at runtime, which would defeat the point of the lazy import.
            messages=cast(Any, messages),
            output_config={"format": {"type": "json_schema", "schema": RESPONSE_SCHEMA}},
        )
        raw_text = next(block.text for block in response.content if block.type == "text")
        items = self._parse_or_count_failure(raw_text)
        spans, location_counts = locate_spans(text, items)
        self.unlocated_spans += location_counts["unlocated_spans"]
        self.relocated_spans += location_counts["relocated_spans"]
        self.ignored_items += location_counts["ignored_items"]
        return spans

    def _parse_or_count_failure(self, raw_text: str) -> list[ParsedItem]:
        """Parse one response body, absorbing a malformed one as no items.

        A response that fails to parse as JSON despite the json_schema
        `output_config` (e.g. a truncated body) must not take the other 299
        examples' already-spent API cost down with it by raising out of
        `predict()` and failing the whole `run_baseline()` call. Counted in
        `self.parse_failures`, which `benchmark.py` surfaces into the result
        JSON's `metadata.parse_failures` the same way it already surfaces
        `bytes_sent_total`, so a run that hits this path stays visible in
        the committed result instead of silently scoring as if the model
        had predicted no entities.
        """
        try:
            return parse_response_text(raw_text)
        except json.JSONDecodeError:
            self.parse_failures += 1
            return []
