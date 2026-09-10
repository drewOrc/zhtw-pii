"""Unit tests for zhtw_pii.eval.metrics."""

import json
from pathlib import Path

import pytest

from zhtw_pii.eval import metrics
from zhtw_pii.eval.types import GoldExample, Span

pytestmark = pytest.mark.unit


def _example(
    example_id: str, text: str, spans: tuple[Span, ...], tier: str = "easy"
) -> GoldExample:
    return GoldExample(id=example_id, text=text, spans=spans, tier=tier)


def test_exact_match_requires_identical_boundaries():
    """A one-character boundary shift must not count as an exact match."""
    gold = Span(0, 2, "PERSON")
    assert metrics.exact_match(gold, Span(0, 2, "PERSON"))
    assert not metrics.exact_match(gold, Span(0, 3, "PERSON"))
    assert not metrics.exact_match(gold, Span(1, 2, "PERSON"))


def test_overlap_match_accepts_any_intersecting_range():
    """Overlap counts a hit as soon as the character ranges intersect."""
    gold = Span(2, 6, "ADDRESS")
    assert metrics.overlap_match(gold, Span(0, 3, "ADDRESS"))
    assert metrics.overlap_match(gold, Span(5, 9, "ADDRESS"))
    assert not metrics.overlap_match(gold, Span(6, 9, "ADDRESS"))
    assert not metrics.overlap_match(gold, Span(0, 2, "ADDRESS"))


def test_score_spans_exact_counts_boundary_miss_as_fp_and_fn():
    """A single off-by-one prediction should count as both a FP and a FN under exact."""
    gold_examples = [_example("e1", "王小明來了", (Span(0, 3, "PERSON"),))]
    predictions = {"e1": [Span(0, 2, "PERSON")]}
    result = metrics.score_spans(gold_examples, predictions, metrics.exact_match)
    assert result["PERSON"] == {"p": 0.0, "r": 0.0, "f1": 0.0, "tp": 0, "fp": 1, "fn": 1}
    assert result["ADDRESS"] == {"p": 0.0, "r": 0.0, "f1": 0.0, "tp": 0, "fp": 0, "fn": 0}
    assert result["micro"]["tp"] == 0
    assert result["micro"]["fp"] == 1
    assert result["micro"]["fn"] == 1


def test_score_spans_overlap_accepts_the_same_boundary_miss():
    """The same off-by-one prediction is a true positive under overlap matching."""
    gold_examples = [_example("e1", "王小明來了", (Span(0, 3, "PERSON"),))]
    predictions = {"e1": [Span(0, 2, "PERSON")]}
    result = metrics.score_spans(gold_examples, predictions, metrics.overlap_match)
    assert result["PERSON"]["tp"] == 1
    assert result["PERSON"]["fp"] == 0
    assert result["PERSON"]["fn"] == 0
    assert result["PERSON"]["f1"] == 1.0


def test_score_spans_micro_aggregates_across_labels():
    """Micro P/R/F1 should sum tp/fp/fn across all three labels, not average per-label F1."""
    gold_examples = [
        _example(
            "e1",
            "陳先生在集賢公司上班",
            (Span(0, 2, "PERSON"), Span(3, 6, "ORG")),
        )
    ]
    predictions = {"e1": [Span(0, 2, "PERSON")]}
    result = metrics.score_spans(gold_examples, predictions, metrics.exact_match)
    assert result["PERSON"]["f1"] == 1.0
    assert result["ORG"]["f1"] == 0.0
    assert result["micro"]["tp"] == 1
    assert result["micro"]["fn"] == 1
    assert result["micro"]["fp"] == 0
    assert result["micro"]["f1"] == pytest.approx(2 / 3, abs=1e-4)


def test_score_spans_with_empty_predictions_dict_treats_missing_id_as_no_predictions():
    """An example id absent from the predictions mapping counts as zero predictions."""
    gold_examples = [_example("e1", "王小明", (Span(0, 3, "PERSON"),))]
    result = metrics.score_spans(gold_examples, {}, metrics.exact_match)
    assert result["PERSON"] == {"p": 0.0, "r": 0.0, "f1": 0.0, "tp": 0, "fp": 0, "fn": 1}


def test_greedy_matching_claims_at_most_one_prediction_per_gold_span():
    """Two identical predicted spans should not both count as true positives for one gold span."""
    gold_examples = [_example("e1", "王小明來了", (Span(0, 3, "PERSON"),))]
    predictions = {"e1": [Span(0, 3, "PERSON"), Span(0, 3, "PERSON")]}
    result = metrics.score_spans(gold_examples, predictions, metrics.exact_match)
    assert result["PERSON"] == {
        "p": 0.5,
        "r": 1.0,
        "f1": round(2 / 3, 4),
        "tp": 1,
        "fp": 1,
        "fn": 0,
    }


def test_overlap_wide_prediction_spanning_two_golds_scores_fp_zero():
    """Documents a known greedy-matching asymmetry; see metrics.py's module docstring.

    One over-wide prediction that overlaps two separate gold spans of the
    same label is scored as a single match plus a miss (tp=1, fn=1), never
    as an imprecise prediction with a false-positive penalty (fp=0). This
    is the mirror image of
    test_greedy_matching_claims_at_most_one_prediction_per_gold_span (two
    narrow predictions against one gold: fp=1, not fn). Both are accepted,
    documented behavior of one-to-one greedy matching, not bugs to fix;
    the v0 test set never has two same-label gold spans in one example, so
    this path is currently dormant and this test exists to catch a change
    in it, not to endorse it as correct.
    """
    gold_examples = [
        _example(
            "e1",
            "台北市中正區忠孝路一段1號、新北市板橋區文化路二段2號",
            (Span(0, 9, "ADDRESS"), Span(10, 19, "ADDRESS")),
        )
    ]
    predictions = {"e1": [Span(0, 19, "ADDRESS")]}
    result = metrics.score_spans(gold_examples, predictions, metrics.overlap_match)
    assert result["ADDRESS"] == {
        "p": 1.0,
        "r": 0.5,
        "f1": round(2 / 3, 4),
        "tp": 1,
        "fp": 0,
        "fn": 1,
    }


def test_compute_negatives_fpr_counts_examples_not_spans():
    """FPR is the fraction of negative examples with at least one prediction, any label."""
    gold_examples = [
        _example("n1", "訂單編號A1", (), tier="negative"),
        _example("n2", "訂單編號B2", (), tier="negative"),
        _example("n3", "訂單編號C3", (), tier="negative"),
    ]
    predictions = {"n1": [Span(0, 2, "ORG"), Span(4, 6, "PERSON")], "n2": []}
    result = metrics.compute_negatives(gold_examples, predictions)
    assert result == {"n": 3, "examples_with_any_prediction": 1, "fpr": round(1 / 3, 4)}


def test_compute_negatives_on_empty_tier_reports_zero_not_a_division_error():
    """No negative examples in the input should return a defined 0.0 FPR, not raise."""
    result = metrics.compute_negatives([], {})
    assert result == {"n": 0, "examples_with_any_prediction": 0, "fpr": 0.0}


def test_false_entities_per_1000_chars_counts_exact_fp_across_all_tiers():
    """The rate should be (total exact FP) / (total chars) * 1000, including negatives."""
    gold_examples = [
        _example("e1", "一二三四五", (), tier="negative"),  # 5 chars
        _example("e2", "六七八九十", (), tier="easy"),  # 5 chars
    ]
    predictions = {"e1": [Span(0, 2, "ORG")], "e2": [Span(0, 2, "PERSON")]}
    rate = metrics.compute_false_entities_per_1000_chars(gold_examples, predictions)
    assert rate == round(2 / 10 * 1000, 4)


def test_false_entities_per_1000_chars_on_empty_input_is_zero():
    """Zero total characters must not raise a division error."""
    assert metrics.compute_false_entities_per_1000_chars([], {}) == 0.0


def test_compute_by_tier_excludes_negative_tier():
    """by_tier covers easy/medium/hard only; negative has no positive spans to score."""
    gold_examples = [
        _example("e1", "王小明", (Span(0, 3, "PERSON"),), tier="easy"),
        _example("n1", "訂單編號", (), tier="negative"),
    ]
    predictions = {"e1": [Span(0, 3, "PERSON")]}
    result = metrics.compute_by_tier(gold_examples, predictions)
    assert set(result) == {"easy", "medium", "hard"}
    assert result["easy"] == {"exact_micro_f1": 1.0, "overlap_micro_f1": 1.0}
    assert result["medium"]["exact_micro_f1"] == 0.0


def test_percentile_matches_hand_computed_linear_interpolation():
    """p50 and p95 of a known small sample should match manual linear interpolation."""
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert metrics.percentile(values, 50) == 30.0
    assert metrics.percentile(values, 0) == 10.0
    assert metrics.percentile(values, 100) == 50.0
    # rank = (5-1) * 0.95 = 3.8 -> interpolate between index 3 (40) and 4 (50)
    assert metrics.percentile(values, 95) == pytest.approx(48.0)


def test_percentile_on_empty_input_is_zero_not_an_error():
    """No timed samples (e.g. test set smaller than warmup) must not raise."""
    assert metrics.percentile([], 50) == 0.0


def test_compute_latency_stats_excludes_warmup_from_n_but_records_the_count():
    """n in the returned stats is the count of timed (post-warmup) samples only."""
    timed = [1.0, 2.0, 3.0, 4.0, 5.0]
    result = metrics.compute_latency_stats(timed, warmup=10)
    assert result["n"] == 5
    assert result["warmup"] == 10
    assert result["mean"] == 3.0
    assert result["p50"] == 3.0


def test_load_gold_examples_round_trips_the_frozen_schema(tmp_path: Path):
    """Loading a hand-written JSONL row should reproduce its id, text, spans, and tier."""
    path = tmp_path / "test.jsonl"
    row = {
        "id": "easy_001",
        "text": "姓名：陳彥。",
        "entities": [{"start": 3, "end": 5, "label": "PERSON"}],
        "tier": "easy",
        "seed": 42,
        "template_id": "rc_02",
    }
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    examples = metrics.load_gold_examples(path)
    assert len(examples) == 1
    assert examples[0].id == "easy_001"
    assert examples[0].text == "姓名：陳彥。"
    assert examples[0].spans == (Span(3, 5, "PERSON"),)
    assert examples[0].tier == "easy"


def test_load_gold_examples_skips_blank_lines(tmp_path: Path):
    """A stray trailing blank line in the JSONL file should not raise a JSON error."""
    path = tmp_path / "test.jsonl"
    row = {
        "id": "e1",
        "text": "x",
        "entities": [],
        "tier": "negative",
        "seed": 42,
        "template_id": "t",
    }
    path.write_text(json.dumps(row) + "\n\n", encoding="utf-8")
    examples = metrics.load_gold_examples(path)
    assert len(examples) == 1


def test_sha256_file_matches_hashlib_reference(tmp_path: Path):
    """sha256_file should match Python's own hashlib digest of the same bytes."""
    import hashlib

    path = tmp_path / "data.bin"
    path.write_bytes(b"zhtw-pii benchmark fixture")
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    assert metrics.sha256_file(path) == expected
