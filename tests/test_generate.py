"""Unit tests for zhtw_pii.data.generate."""

import hashlib
import json
import random

import pytest

from zhtw_pii.data import generate

pytestmark = pytest.mark.unit


class _ScriptedChoice(random.Random):
    """A random.Random whose .choice() replays a fixed scripted sequence.

    Subclassing random.Random (rather than a bare duck-typed stub) keeps the
    type checker happy while letting the test dictate the exact draw order.
    """

    def __init__(self, values: list[object]) -> None:
        super().__init__()
        self._values = list(values)
        self.calls = 0

    def choice(self, seq):  # type: ignore[override]
        value = self._values[self.calls]
        self.calls += 1
        return value


def test_same_seed_generates_byte_identical_jsonl(tmp_path):
    """Two runs with the same seed should write identical bytes to disk."""
    first_path = tmp_path / "first.jsonl"
    second_path = tmp_path / "second.jsonl"
    generate.write_jsonl(generate.generate_dataset(seed=42), first_path)
    generate.write_jsonl(generate.generate_dataset(seed=42), second_path)
    first_hash = hashlib.sha256(first_path.read_bytes()).hexdigest()
    second_hash = hashlib.sha256(second_path.read_bytes()).hexdigest()
    assert first_hash == second_hash


def test_different_seed_generates_different_content(tmp_path):
    """A different seed should change the serialized byte content."""
    path_a = tmp_path / "seed42.jsonl"
    path_b = tmp_path / "seed43.jsonl"
    generate.write_jsonl(generate.generate_dataset(seed=42), path_a)
    generate.write_jsonl(generate.generate_dataset(seed=43), path_b)
    assert path_a.read_bytes() != path_b.read_bytes()


def test_default_tier_counts_match_spec_and_total_300():
    """Default generation should produce 80/100/70/50 rows per tier, 300 total."""
    examples = generate.generate_dataset(seed=42)
    counts = {tier: 0 for tier in generate.DEFAULT_TIER_COUNTS}
    for example in examples:
        counts[example.tier] += 1
    assert counts == generate.DEFAULT_TIER_COUNTS
    assert len(examples) == 300


def test_every_entity_span_is_a_valid_labeled_char_range():
    """Every entity's offsets should bound a non-empty, correctly labeled span."""
    examples = generate.generate_dataset(seed=42)
    assert examples
    for example in examples:
        for entity in example.entities:
            assert 0 <= entity.start < entity.end <= len(example.text)
            assert example.text[entity.start : entity.end]
            assert entity.label in {"PERSON", "ADDRESS", "ORG"}


def test_negative_tier_examples_have_no_entities():
    """Negative-tier rows are number-dense but must carry zero PII entities."""
    examples = generate.generate_dataset(seed=42)
    negative_examples = [example for example in examples if example.tier == "negative"]
    assert len(negative_examples) == generate.DEFAULT_TIER_COUNTS["negative"]
    assert all(example.entities == [] for example in negative_examples)


def test_blocklisted_name_never_returned_even_when_rng_tries_it_first():
    """Rejection sampling must retry past a blocklisted name, not return it."""
    scripted_rng = _ScriptedChoice(["王", 2, "小", "明", "陳", 1, "宇"])
    profile = generate.NoiseProfile(
        strip_punctuation=False, honorific=False, fullwidth=False, partial_address=False
    )
    name = generate.generate_person(scripted_rng, {"王小明"}, profile)
    assert name == "陳宇"
    assert "王小明" not in name
    assert scripted_rng.calls == 7


def test_jsonl_lines_are_valid_json_with_expected_keys(tmp_path):
    """Each JSONL line must parse and expose exactly the documented schema."""
    path = tmp_path / "test.jsonl"
    generate.write_jsonl(generate.generate_dataset(seed=42, tier_counts={"easy": 3}), path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    for line in lines:
        row = json.loads(line)
        assert set(row.keys()) == {"id", "text", "entities", "tier", "seed", "template_id"}
        for entity in row["entities"]:
            assert set(entity.keys()) == {"start", "end", "label"}
