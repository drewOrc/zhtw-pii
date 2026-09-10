"""CLI benchmark runner: evaluates baselines against the frozen test set.

Writes `results/benchmark/v0/<key>.json` (one per registry key: regex,
presidio, gliner2_en, gliner2_zh, llm) and
`results/benchmark/v0/predictions/<key>.jsonl`. A baseline that cannot run
(missing package, model load failure, missing credential, or any
unexpected error mid-run) is written as `"status": "unevaluated"` with a
`reason`, never silently skipped, and its failure is what makes the
process exit non-zero; a successfully evaluated baseline never affects
the exit code.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from platform import platform as platform_string
from platform import processor, python_version
from typing import Any

from zhtw_pii.eval import metrics, registry
from zhtw_pii.eval.types import BaselineUnavailable, GoldExample, Span

DEFAULT_TESTSET = Path("data/testset/v0/test.jsonl")
DEFAULT_OUT_DIR = Path("results/benchmark/v0")
DEFAULT_WARMUP = 10


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for `python -m zhtw_pii.eval.benchmark`."""
    parser = argparse.ArgumentParser(description="Run the zhtw-pii baseline benchmark.")
    parser.add_argument(
        "--testset", type=Path, default=DEFAULT_TESTSET, help="frozen JSONL test set"
    )
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT_DIR, help="output directory for result JSON"
    )
    parser.add_argument(
        "--baselines",
        type=str,
        default="all",
        help="comma-separated selectors (regex, presidio, gliner2, llm) or 'all'",
    )
    parser.add_argument(
        "--warmup", type=int, default=DEFAULT_WARMUP, help="examples excluded from latency stats"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="evaluate only the first N examples (dev/testing only)",
    )
    return parser


def _hardware_string() -> str:
    return f"{platform_string()} ({processor() or 'unknown processor'})"


def _base_metadata_fields(
    testset_path: Path, testset_sha256: str, n_examples: int
) -> dict[str, Any]:
    return {
        "hardware": _hardware_string(),
        "python": python_version(),
        "date_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "testset_path": str(testset_path),
        "testset_sha256": testset_sha256,
        "n_examples": n_examples,
    }


def _unevaluated_result(
    key: str, reason: str, base_metadata: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    return {
        "baseline": key,
        "status": "unevaluated",
        "reason": reason,
        "metadata": {
            "model_id": None,
            "model_version": None,
            "size_mb": None,
            "data_leaves_machine": None,
            "bytes_sent": None,
            "package_versions": {},
            **base_metadata,
        },
        "config": config,
        "metrics": None,
        "latency_ms": None,
        "predictions_path": None,
    }


def _write_predictions(
    path: Path, gold_examples: Sequence[GoldExample], predictions: dict[str, list[Span]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for example in gold_examples:
            row = {
                "id": example.id,
                "spans": [span.to_json_dict() for span in predictions.get(example.id, [])],
            }
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def _write_result(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def run_baseline(
    key: str,
    gold_examples: Sequence[GoldExample],
    warmup: int,
    out_dir: Path,
    base_metadata: dict[str, Any],
) -> dict[str, Any]:
    """Run one registry key end to end and return its result dict.

    Never raises: an unknown key, a missing package, a failed model load,
    or an unexpected exception during prediction all become an
    "unevaluated" result carrying the real error text as `reason`, so one
    baseline's failure cannot take down the others in the same run.
    """
    try:
        adapter = registry.build_adapter(key)
    except KeyError as exc:
        return _unevaluated_result(key, str(exc), base_metadata, {})

    config = {
        "label_mapping": dict(getattr(adapter, "label_mapping", {})),
        "params": dict(getattr(adapter, "params", {})),
    }

    try:
        baseline_metadata = adapter.load()
    except BaselineUnavailable as exc:
        return _unevaluated_result(key, exc.reason, base_metadata, config)
    except Exception as exc:  # noqa: BLE001 - any load failure is "unevaluated", not a crash
        return _unevaluated_result(key, f"{type(exc).__name__}: {exc}", base_metadata, config)

    predictions: dict[str, list[Span]] = {}
    timed_ms: list[float] = []
    try:
        for index, example in enumerate(gold_examples):
            started_at = time.perf_counter()
            spans = adapter.predict(example.text)
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            predictions[example.id] = spans
            if index >= warmup:
                timed_ms.append(elapsed_ms)
    except Exception as exc:  # noqa: BLE001 - a mid-run failure is "unevaluated", not a crash
        return _unevaluated_result(key, f"{type(exc).__name__}: {exc}", base_metadata, config)

    bytes_sent = getattr(adapter, "bytes_sent_total", baseline_metadata.bytes_sent)

    predictions_path = out_dir / "predictions" / f"{key}.jsonl"
    _write_predictions(predictions_path, gold_examples, predictions)

    exact = metrics.score_spans(gold_examples, predictions, metrics.exact_match)
    overlap = metrics.score_spans(gold_examples, predictions, metrics.overlap_match)
    negatives = metrics.compute_negatives(gold_examples, predictions)
    false_entities = metrics.compute_false_entities_per_1000_chars(gold_examples, predictions)
    by_tier = metrics.compute_by_tier(gold_examples, predictions)

    return {
        "baseline": key,
        "status": "evaluated",
        "reason": None,
        "metadata": {
            "model_id": baseline_metadata.model_id,
            "model_version": baseline_metadata.model_version,
            "size_mb": baseline_metadata.size_mb,
            "data_leaves_machine": baseline_metadata.data_leaves_machine,
            "bytes_sent": bytes_sent,
            "package_versions": baseline_metadata.package_versions,
            **base_metadata,
        },
        "config": config,
        "metrics": {
            "exact": exact,
            "overlap": overlap,
            "negatives": negatives,
            "false_entities_per_1000_chars": false_entities,
            "by_tier": by_tier,
        },
        "latency_ms": metrics.compute_latency_stats(timed_ms, warmup),
        "predictions_path": str(predictions_path),
    }


def run_all(args: argparse.Namespace) -> int:
    """Run every baseline `args.baselines` resolves to; return the process exit code."""
    testset_path: Path = args.testset
    gold_examples = metrics.load_gold_examples(testset_path)
    if args.limit is not None:
        gold_examples = gold_examples[: args.limit]
    testset_sha256 = metrics.sha256_file(testset_path)
    base_metadata = _base_metadata_fields(testset_path, testset_sha256, len(gold_examples))
    warmup = min(args.warmup, len(gold_examples))

    keys = registry.resolve_selectors(args.baselines.split(","))

    exit_code = 0
    for key in keys:
        result = run_baseline(key, gold_examples, warmup, args.out, base_metadata)
        _write_result(args.out / f"{key}.json", result)
        if result["status"] == "unevaluated":
            exit_code = 1
            print(f"[{key}] unevaluated: {result['reason']}", file=sys.stderr)
        else:
            micro_f1 = result["metrics"]["exact"]["micro"]["f1"]
            print(f"[{key}] evaluated: exact micro F1 = {micro_f1}")
    return exit_code


def main(argv: Sequence[str] | None = None) -> None:
    """Entry point for `python -m zhtw_pii.eval.benchmark`."""
    args = build_arg_parser().parse_args(argv)
    sys.exit(run_all(args))


if __name__ == "__main__":
    main()
