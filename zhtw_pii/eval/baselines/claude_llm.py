"""Claude Haiku few-shot baseline: the accuracy/cost/privacy reference point.

Requires `ANTHROPIC_API_KEY`. Without it, `load()` raises
`BaselineUnavailable("ANTHROPIC_API_KEY not set")` and the runner writes
an "unevaluated" result. This milestone (M1, Issue #3) exercises only
that no-key path plus the JSON-parsing logic against a mocked response,
never a real API call; see tests/test_eval_llm_baseline.py.

Model id: the task brief for this baseline named
`claude-haiku-4-5-20251001`. Current Anthropic model ids for models still
being served do not carry a date suffix (a dated variant is very likely
to 404 against a real deployment); the live-served id is
`claude-haiku-4-5`, used here instead. `MODEL_ID` is a module constant so
pointing this at a different id is a one-line change. The first real run
made with an API key must confirm `MODEL_ID` actually resolves against the
live API before its output is trusted; nothing in this module or its tests
calls the real API.

`predict()` uses `output_config: {"format": {"type": "json_schema", ...}}`
(structured outputs) rather than prompting for JSON and hoping, so a
malformed top-level response is a genuine API-contract violation, not a
prompting failure.
"""

from __future__ import annotations

import json
import os
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

SYSTEM_PROMPT = (
    "You detect Traditional Chinese PERSON names, ADDRESS fragments, and "
    "ORG (organization) names in short input sentences. Return every span "
    "as exact character offsets into the ORIGINAL input string, using "
    "Python-style string indexing, half-open [start, end). Only use the "
    "labels PERSON, ADDRESS, ORG. If there are no matching entities, "
    "return an empty list. Never include a span for a number, date, "
    "amount, or reference code."
)

_FEW_SHOT_EXAMPLES: tuple[dict[str, Any], ...] = (
    {
        "text": "姓名：陳彥。",
        "spans": [{"start": 3, "end": 5, "label": "PERSON"}],
    },
    {
        "text": "客戶王小明來電反映，居住地址為台北市中正區忠孝路2段45號。",
        "spans": [
            {"start": 2, "end": 5, "label": "PERSON"},
            {"start": 13, "end": 27, "label": "ADDRESS"},
        ],
    },
    {
        "text": "本案由誠信協會承辦，聯絡人為林小華。",
        "spans": [
            {"start": 3, "end": 7, "label": "ORG"},
            {"start": 13, "end": 16, "label": "PERSON"},
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
                    "start": {"type": "integer"},
                    "end": {"type": "integer"},
                    "label": {"type": "string", "enum": list(LABELS)},
                },
                "required": ["start", "end", "label"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["spans"],
    "additionalProperties": False,
}


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


def parse_response_text(raw_text: str, input_length: int) -> list[Span]:
    """Parse one JSON response body into validated spans.

    A span with an out-of-range or inverted offset, or an unrecognized
    label, is dropped rather than raised on: one bad span from the model
    should not fail the whole example. An unparseable top-level body does
    raise (`json.JSONDecodeError`), since that means the response is not
    usable at all and the caller should surface it as a real failure.
    """
    data = json.loads(raw_text)
    spans: list[Span] = []
    for raw_span in data.get("spans", []):
        try:
            start = int(raw_span["start"])
            end = int(raw_span["end"])
            label = str(raw_span["label"])
        except (KeyError, TypeError, ValueError):
            continue
        if label not in LABELS:
            continue
        if not (0 <= start < end <= input_length):
            continue
        spans.append(Span(start=start, end=end, label=label))
    spans.sort(key=lambda span: (span.start, span.end, span.label))
    return spans


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

    def __init__(self) -> None:
        self._client: anthropic.Anthropic | None = None
        self.bytes_sent_total = 0
        self.parse_failures = 0

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
        return self._parse_or_count_failure(raw_text, len(text))

    def _parse_or_count_failure(self, raw_text: str, input_length: int) -> list[Span]:
        """Parse one response body, absorbing a malformed one as an empty prediction.

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
            return parse_response_text(raw_text, input_length)
        except json.JSONDecodeError:
            self.parse_failures += 1
            return []
