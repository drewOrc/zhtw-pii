"""Scoring functions for the benchmark runner.

Two matching rules are computed for every baseline:

- **exact**: a prediction counts as a true positive only if `(start, end,
  label)` matches a gold span exactly. This is the primary metric.
- **overlap**: a prediction counts as a true positive if it shares a label
  with a gold span and their character ranges intersect at all. This is
  more forgiving of boundary errors and is reported alongside exact, never
  in place of it.

Both use greedy one-to-one matching: each gold span can be claimed by at
most one predicted span and vice versa, processed in the order the spans
appear in the input lists. Unclaimed gold spans are false negatives;
unclaimed predicted spans are false positives.

This pairing is intentionally asymmetric when one example has two gold
spans of the same label. Two overly narrow predictions against one gold
span score one tp and one fp: the first prediction claims the gold span,
the second finds no unclaimed gold left and becomes a false positive. One
overly wide prediction spanning two gold spans of that label instead
scores one tp and one fn: the prediction claims the first gold span it is
checked against, and the second gold span finds no unclaimed prediction
left, so it becomes a false negative rather than the wide prediction also
counting as a false positive. This is accepted for now, not fixed, because
one-to-one greedy pairing is a simple O(n) algorithm and the v0 test set
never repeats a label within one example, so the path is dormant; see
`test_overlap_wide_prediction_spanning_two_golds_scores_fp_zero` in
`tests/test_eval_metrics.py`, which locks in the exact current behavior.
A v1 test set with repeated same-label entities per example will exercise
this path, and may call for a different matching strategy (e.g. optimal
bipartite matching) if the asymmetry then proves misleading.

`false_entities_per_1000_chars` counts **exact-match** false positives
(not overlap) across all 300 examples, including the negative tier, and
normalizes by total input length. Exact is used here, not overlap,
because it is the metric this project treats as primary throughout; a
prediction that overlaps a gold span but has the wrong boundary is
counted as a (fp, fn) pair under exact and does not inflate this number
beyond what the primary metric already reflects. See
`docs/benchmark.md`'s Method section for the same explanation in the
published table.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from zhtw_pii.eval.types import GoldExample, Span

LABELS: tuple[str, ...] = ("PERSON", "ADDRESS", "ORG")
TIER_ORDER: tuple[str, ...] = ("easy", "medium", "hard")


def round4(value: float) -> float:
    """Round a metric to 4 decimal places, the fixed precision for results JSON."""
    return round(value + 0.0, 4)


def load_gold_examples(path: Path) -> list[GoldExample]:
    """Load the frozen test set's gold spans, in file order."""
    examples: list[GoldExample] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            spans = tuple(
                Span(start=e["start"], end=e["end"], label=e["label"]) for e in row["entities"]
            )
            examples.append(
                GoldExample(id=row["id"], text=row["text"], spans=spans, tier=row["tier"])
            )
    return examples


def sha256_file(path: Path) -> str:
    """Return the hex SHA256 digest of a file's raw bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exact_match(gold: Span, pred: Span) -> bool:
    """True if a predicted span matches a gold span's exact character range."""
    return gold.start == pred.start and gold.end == pred.end


def overlap_match(gold: Span, pred: Span) -> bool:
    """True if a predicted span's character range intersects a gold span's."""
    return gold.start < pred.end and pred.start < gold.end


def _greedy_match(
    gold_spans: Sequence[Span], pred_spans: Sequence[Span], is_match: Callable[[Span, Span], bool]
) -> tuple[int, int, int]:
    """Greedily pair spans of one label and return (tp, fp, fn) for the pair.

    Every gold span is checked against the still-unclaimed predicted spans
    in order; the first match wins and is removed from the pool. Predicted
    spans left unclaimed at the end are false positives.
    """
    remaining_pred = list(pred_spans)
    true_positives = 0
    false_negatives = 0
    for gold in gold_spans:
        claimed_index = None
        for index, pred in enumerate(remaining_pred):
            if is_match(gold, pred):
                claimed_index = index
                break
        if claimed_index is None:
            false_negatives += 1
        else:
            true_positives += 1
            remaining_pred.pop(claimed_index)
    return true_positives, len(remaining_pred), false_negatives


def _prf1(
    true_positives: int, false_positives: int, false_negatives: int
) -> dict[str, float | int]:
    """Compute precision, recall, and F1 from raw counts."""
    predicted = true_positives + false_positives
    actual = true_positives + false_negatives
    precision = true_positives / predicted if predicted else 0.0
    recall = true_positives / actual if actual else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "p": round4(precision),
        "r": round4(recall),
        "f1": round4(f1),
        "tp": true_positives,
        "fp": false_positives,
        "fn": false_negatives,
    }


def score_spans(
    gold_examples: Sequence[GoldExample],
    predictions: Mapping[str, Sequence[Span]],
    is_match: Callable[[Span, Span], bool],
) -> dict[str, dict[str, float | int]]:
    """Score predictions against gold spans under one matching rule.

    Returns one P/R/F1 block per label in `LABELS`, plus a `micro` block
    summed across labels. `predictions` is keyed by example id; an example
    with no entry is treated as an empty prediction list.
    """
    per_label_counts = {label: [0, 0, 0] for label in LABELS}
    for example in gold_examples:
        pred_spans = predictions.get(example.id, ())
        for label in LABELS:
            gold_label_spans = [span for span in example.spans if span.label == label]
            pred_label_spans = [span for span in pred_spans if span.label == label]
            tp, fp, fn = _greedy_match(gold_label_spans, pred_label_spans, is_match)
            counts = per_label_counts[label]
            counts[0] += tp
            counts[1] += fp
            counts[2] += fn

    result = {label: _prf1(*counts) for label, counts in per_label_counts.items()}
    micro_tp = sum(counts[0] for counts in per_label_counts.values())
    micro_fp = sum(counts[1] for counts in per_label_counts.values())
    micro_fn = sum(counts[2] for counts in per_label_counts.values())
    result["micro"] = _prf1(micro_tp, micro_fp, micro_fn)
    return result


def compute_negatives(
    gold_examples: Sequence[GoldExample], predictions: Mapping[str, Sequence[Span]]
) -> dict[str, float | int]:
    """Compute the false-positive rate on the negative tier.

    A negative example "fires" if the baseline predicts any span at all
    for it, regardless of label; FPR is the fraction of negative examples
    that fire.
    """
    negative_examples = [example for example in gold_examples if example.tier == "negative"]
    fired = sum(1 for example in negative_examples if predictions.get(example.id))
    n = len(negative_examples)
    return {
        "n": n,
        "examples_with_any_prediction": fired,
        "fpr": round4(fired / n) if n else 0.0,
    }


def compute_false_entities_per_1000_chars(
    gold_examples: Sequence[GoldExample], predictions: Mapping[str, Sequence[Span]]
) -> float:
    """Compute exact-match false positives per 1000 characters, over all tiers."""
    total_chars = sum(len(example.text) for example in gold_examples)
    total_false_positives = 0
    for example in gold_examples:
        pred_spans = predictions.get(example.id, ())
        for label in LABELS:
            gold_label_spans = [span for span in example.spans if span.label == label]
            pred_label_spans = [span for span in pred_spans if span.label == label]
            _, fp, _ = _greedy_match(gold_label_spans, pred_label_spans, exact_match)
            total_false_positives += fp
    if total_chars == 0:
        return 0.0
    return round4(total_false_positives / total_chars * 1000)


def compute_by_tier(
    gold_examples: Sequence[GoldExample], predictions: Mapping[str, Sequence[Span]]
) -> dict[str, dict[str, float]]:
    """Compute micro exact and overlap F1 for each of easy/medium/hard.

    The negative tier is excluded here; it has no positive spans to score
    and is covered separately by `compute_negatives`.
    """
    result: dict[str, dict[str, float]] = {}
    for tier in TIER_ORDER:
        tier_examples = [example for example in gold_examples if example.tier == tier]
        exact_scores = score_spans(tier_examples, predictions, exact_match)
        overlap_scores = score_spans(tier_examples, predictions, overlap_match)
        result[tier] = {
            "exact_micro_f1": exact_scores["micro"]["f1"],
            "overlap_micro_f1": overlap_scores["micro"]["f1"],
        }
    return result


def percentile(values: Sequence[float], pct: float) -> float:
    """Linear-interpolation percentile, matching numpy's default method.

    `pct` is in `[0, 100]`. Returns 0.0 for an empty input rather than
    raising, since a baseline with zero timed calls (test set smaller than
    the warmup count) is a valid, if degenerate, input.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (pct / 100)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[int(rank)]
    lower_value = ordered[lower] * (upper - rank)
    upper_value = ordered[upper] * (rank - lower)
    return lower_value + upper_value


def compute_latency_stats(timed_ms: Sequence[float], warmup: int) -> dict[str, float | int]:
    """Summarize per-example latency in milliseconds, already warmup-excluded."""
    mean = sum(timed_ms) / len(timed_ms) if timed_ms else 0.0
    return {
        "p50": round4(percentile(timed_ms, 50)),
        "p95": round4(percentile(timed_ms, 95)),
        "mean": round4(mean),
        "n": len(timed_ms),
        "warmup": warmup,
    }
