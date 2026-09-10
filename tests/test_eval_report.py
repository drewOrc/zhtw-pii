"""Unit tests for zhtw_pii.eval.report.

All tests monkeypatch report.RESULTS_DIR / README_PATH / BENCHMARK_DOC_PATH
to tmp_path locations, so nothing here touches the real results/ or
README.md in the repo.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zhtw_pii.eval import report

pytestmark = pytest.mark.unit

README_TEMPLATE = """# zhtw-pii

Some hand-written intro.

## Benchmark

<!-- benchmark:start -->
placeholder
<!-- benchmark:end -->

## Some other section

Untouched hand-written content.
"""


def _evaluated_result(baseline: str, f1: float = 0.8) -> dict[str, object]:
    per_label = {"p": f1, "r": f1, "f1": f1, "tp": 1, "fp": 0, "fn": 0}
    micro = dict(per_label)
    return {
        "baseline": baseline,
        "status": "evaluated",
        "reason": None,
        "metadata": {
            "model_id": f"{baseline}-model",
            "model_version": "1.0",
            "size_mb": 12.34,
            "data_leaves_machine": False,
            "bytes_sent": None,
            "package_versions": {},
            "hardware": "test-hardware",
            "python": "3.11.14",
            "date_utc": "2026-01-01T00:00:00Z",
            "testset_path": "data/testset/v0/test.jsonl",
            "testset_sha256": "deadbeef",
            "n_examples": 300,
        },
        "config": {"label_mapping": {}, "params": {}},
        "metrics": {
            "exact": {
                "PERSON": dict(per_label),
                "ADDRESS": dict(per_label),
                "ORG": dict(per_label),
                "micro": micro,
            },
            "overlap": {
                "PERSON": dict(per_label),
                "ADDRESS": dict(per_label),
                "ORG": dict(per_label),
                "micro": dict(micro),
            },
            "negatives": {"n": 50, "examples_with_any_prediction": 2, "fpr": 0.04},
            "false_entities_per_1000_chars": 1.2345,
            "by_tier": {
                "easy": {"exact_micro_f1": 0.9, "overlap_micro_f1": 0.95},
                "medium": {"exact_micro_f1": 0.8, "overlap_micro_f1": 0.85},
                "hard": {"exact_micro_f1": 0.7, "overlap_micro_f1": 0.75},
            },
        },
        "latency_ms": {"p50": 1.5, "p95": 3.5, "mean": 2.0, "n": 290, "warmup": 10},
        "predictions_path": f"results/benchmark/v0/predictions/{baseline}.jsonl",
    }


def _unevaluated_result(baseline: str, reason: str) -> dict[str, object]:
    return {
        "baseline": baseline,
        "status": "unevaluated",
        "reason": reason,
        "metadata": {
            "model_id": None,
            "model_version": None,
            "size_mb": None,
            "data_leaves_machine": None,
            "bytes_sent": None,
            "package_versions": {},
            "hardware": "test-hardware",
            "python": "3.11.14",
            "date_utc": "2026-01-01T00:00:00Z",
            "testset_path": "data/testset/v0/test.jsonl",
            "testset_sha256": "deadbeef",
            "n_examples": 300,
        },
        "config": {"label_mapping": {}, "params": {}},
        "metrics": None,
        "latency_ms": None,
        "predictions_path": None,
    }


def _setup_fixture(tmp_path: Path, monkeypatch, results: dict[str, dict[str, object]]) -> None:
    results_dir = tmp_path / "results" / "benchmark" / "v0"
    results_dir.mkdir(parents=True)
    for key, result in results.items():
        payload = json.dumps(result, ensure_ascii=False)
        (results_dir / f"{key}.json").write_text(payload, encoding="utf-8")

    readme_path = tmp_path / "README.md"
    readme_path.write_text(README_TEMPLATE, encoding="utf-8")

    monkeypatch.setattr(report, "RESULTS_DIR", results_dir)
    monkeypatch.setattr(report, "README_PATH", readme_path)
    monkeypatch.setattr(report, "BENCHMARK_DOC_PATH", tmp_path / "docs" / "benchmark.md")


def test_render_main_table_shows_real_numbers_for_an_evaluated_baseline(tmp_path, monkeypatch):
    _setup_fixture(tmp_path, monkeypatch, {"regex": _evaluated_result("regex")})
    benchmark_doc, _ = report.render()
    assert "0.8000" in benchmark_doc
    assert "Regex + lexicon baseline" in benchmark_doc


def test_render_main_table_shows_unevaluated_not_a_fake_number(tmp_path, monkeypatch):
    unevaluated = {"llm": _unevaluated_result("llm", "ANTHROPIC_API_KEY not set")}
    _setup_fixture(tmp_path, monkeypatch, unevaluated)
    benchmark_doc, _ = report.render()
    assert "unevaluated" in benchmark_doc
    assert "ANTHROPIC_API_KEY not set" in benchmark_doc


def test_render_is_deterministic_across_two_calls(tmp_path, monkeypatch):
    _setup_fixture(
        tmp_path,
        monkeypatch,
        {
            "regex": _evaluated_result("regex"),
            "llm": _unevaluated_result("llm", "ANTHROPIC_API_KEY not set"),
        },
    )
    first_doc, first_readme = report.render()
    second_doc, second_readme = report.render()
    assert first_doc == second_doc
    assert first_readme == second_readme


def test_write_then_check_reports_up_to_date(tmp_path, monkeypatch, capsys):
    _setup_fixture(tmp_path, monkeypatch, {"regex": _evaluated_result("regex")})
    report.write()
    exit_code = report.check()
    assert exit_code == 0


def test_check_fails_after_hand_editing_the_rendered_doc(tmp_path, monkeypatch):
    _setup_fixture(tmp_path, monkeypatch, {"regex": _evaluated_result("regex")})
    report.write()
    report.BENCHMARK_DOC_PATH.write_text("hand-edited, does not match results/", encoding="utf-8")
    assert report.check() == 1


def test_check_fails_after_hand_editing_the_readme_table(tmp_path, monkeypatch):
    _setup_fixture(tmp_path, monkeypatch, {"regex": _evaluated_result("regex")})
    report.write()
    tampered = report.README_PATH.read_text(encoding="utf-8").replace("0.8000", "0.9999")
    report.README_PATH.write_text(tampered, encoding="utf-8")
    assert report.check() == 1


def test_check_fails_when_benchmark_doc_has_never_been_written(tmp_path, monkeypatch):
    _setup_fixture(tmp_path, monkeypatch, {"regex": _evaluated_result("regex")})
    assert not report.BENCHMARK_DOC_PATH.exists()
    assert report.check() == 1


def test_write_preserves_readme_content_outside_the_markers(tmp_path, monkeypatch):
    _setup_fixture(tmp_path, monkeypatch, {"regex": _evaluated_result("regex")})
    report.write()
    updated_readme = report.README_PATH.read_text(encoding="utf-8")
    assert "Some hand-written intro." in updated_readme
    assert "Untouched hand-written content." in updated_readme
    assert "placeholder" not in updated_readme


def test_render_readme_section_raises_a_clear_error_when_markers_are_missing(tmp_path, monkeypatch):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    regex_payload = json.dumps(_evaluated_result("regex"))
    (results_dir / "regex.json").write_text(regex_payload, encoding="utf-8")
    readme_path = tmp_path / "README.md"
    readme_path.write_text("# No markers here\n", encoding="utf-8")
    monkeypatch.setattr(report, "RESULTS_DIR", results_dir)
    monkeypatch.setattr(report, "README_PATH", readme_path)

    with pytest.raises(ValueError, match="benchmark:start"):
        report.render()


def test_by_tier_table_lists_only_evaluated_baselines(tmp_path, monkeypatch):
    _setup_fixture(
        tmp_path,
        monkeypatch,
        {"regex": _evaluated_result("regex"), "llm": _unevaluated_result("llm", "no key")},
    )
    results = report.load_results(report.RESULTS_DIR)
    table = report.render_by_tier_table(results)
    assert "Regex + lexicon baseline" in table
    assert "Claude Haiku 4.5" not in table


def test_load_results_only_reads_files_that_exist(tmp_path):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    regex_payload = json.dumps(_evaluated_result("regex"))
    (results_dir / "regex.json").write_text(regex_payload, encoding="utf-8")
    results = report.load_results(results_dir)
    assert set(results) == {"regex"}


def test_escape_reason_collapses_newlines_and_extra_whitespace():
    messy = "line one\n   line two\t\ttabbed"
    assert report._escape_reason(messy) == "line one line two tabbed"


def test_unevaluated_reason_with_a_pipe_character_does_not_break_the_bullet_list(
    tmp_path, monkeypatch
):
    """A reason string containing '|' must not corrupt markdown table syntax."""
    reason = "install failed: expected 'a' | 'b', got 'c'"
    _setup_fixture(tmp_path, monkeypatch, {"llm": _unevaluated_result("llm", reason)})
    benchmark_doc, _ = report.render()
    # The reason lives in a bullet list, not inside a table row.
    assert reason in benchmark_doc
    main_table_lines = [
        line for line in benchmark_doc.splitlines() if line.startswith("| Claude Haiku")
    ]
    assert main_table_lines
    assert "expected" not in main_table_lines[0]
