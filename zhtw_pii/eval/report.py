"""Render results/*.json into docs/benchmark.md and README.md's marked region.

`results/benchmark/v0/*.json` is the single source of truth (ADR-0008);
every number in `docs/benchmark.md` and the README table is read from
there, never typed by hand. `--check` re-renders in memory and diffs
against what is on disk, so a hand-edited number or a stale README table
is a CI failure (`report-check.yml`), not silent drift.

Determinism: nothing here reads the current wall clock. Every date shown
comes from a result file's own `metadata.date_utc` (recorded once, at
benchmark run time); running `make report` twice with unchanged inputs
produces byte-identical output.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import Any

RESULTS_DIR = Path("results/benchmark/v0")
BENCHMARK_DOC_PATH = Path("docs/benchmark.md")
README_PATH = Path("README.md")

README_MARKER_START = "<!-- benchmark:start -->"
README_MARKER_END = "<!-- benchmark:end -->"

# Reading order for every rendered table: weakest to strongest, the LLM
# last as the accuracy/cost/privacy ceiling. Not alphabetical on purpose.
BASELINE_ORDER: tuple[str, ...] = ("regex", "presidio", "gliner2_en", "gliner2_zh", "llm")
BASELINE_DISPLAY_NAMES: dict[str, str] = {
    "regex": "Regex + lexicon baseline",
    "presidio": "Microsoft Presidio",
    "gliner2_en": "GLiNER2-PII (English labels)",
    "gliner2_zh": "GLiNER2-PII (Chinese labels)",
    "llm": "Claude Haiku 4.5 (few-shot)",
}
LABELS: tuple[str, ...] = ("PERSON", "ADDRESS", "ORG")
TIERS: tuple[str, ...] = ("easy", "medium", "hard")

MAIN_TABLE_HEADER = (
    "| System | PERSON F1 | ADDRESS F1 | ORG F1 | Micro F1 (exact) | "
    "Micro F1 (overlap) | FPR (negatives) | Latency p50/p95 (ms) | Size | Data leaves device? |"
)
MAIN_TABLE_SEPARATOR = "|---|---|---|---|---|---|---|---|---|---|"


def load_results(results_dir: Path) -> dict[str, dict[str, Any]]:
    """Load every baseline's result JSON that exists in `results_dir`."""
    results: dict[str, dict[str, Any]] = {}
    for key in BASELINE_ORDER:
        path = results_dir / f"{key}.json"
        if path.exists():
            results[key] = json.loads(path.read_text(encoding="utf-8"))
    return results


def _fmt_float(value: Any, digits: int = 4) -> str:
    return "N/A" if value is None else f"{float(value):.{digits}f}"


def _fmt_bool(value: Any) -> str:
    return "N/A" if value is None else ("yes" if value else "no")


def _fmt_size(size_mb: Any) -> str:
    return "N/A" if size_mb is None else f"{float(size_mb):.2f} MB"


def _escape_reason(reason: str) -> str:
    """Make a free-text failure reason safe to place in a markdown bullet."""
    return " ".join(reason.split())


def _main_table_row(key: str, result: dict[str, Any]) -> str:
    name = BASELINE_DISPLAY_NAMES[key]
    if result["status"] == "unevaluated":
        cells = [name] + ["unevaluated"] * 6 + ["N/A", "N/A"]
        return "| " + " | ".join(cells) + " |"
    metrics_block = result["metrics"]
    exact = metrics_block["exact"]
    latency = result["latency_ms"]
    metadata = result["metadata"]
    cells = [
        name,
        _fmt_float(exact["PERSON"]["f1"]),
        _fmt_float(exact["ADDRESS"]["f1"]),
        _fmt_float(exact["ORG"]["f1"]),
        _fmt_float(exact["micro"]["f1"]),
        _fmt_float(metrics_block["overlap"]["micro"]["f1"]),
        _fmt_float(metrics_block["negatives"]["fpr"]),
        f"{_fmt_float(latency['p50'], 3)} / {_fmt_float(latency['p95'], 3)}",
        _fmt_size(metadata["size_mb"]),
        _fmt_bool(metadata["data_leaves_machine"]),
    ]
    return "| " + " | ".join(cells) + " |"


def render_main_table(results: dict[str, dict[str, Any]]) -> str:
    """Render the primary per-baseline comparison table."""
    rows = [MAIN_TABLE_HEADER, MAIN_TABLE_SEPARATOR]
    rows.extend(_main_table_row(key, results[key]) for key in BASELINE_ORDER if key in results)
    return "\n".join(rows)


def render_unevaluated_section(results: dict[str, dict[str, Any]]) -> str:
    """Render the reason for every unevaluated baseline as a bullet list."""
    unevaluated = [
        (key, result) for key, result in results.items() if result["status"] == "unevaluated"
    ]
    if not unevaluated:
        return "All requested baselines evaluated; none were skipped."
    lines = [
        f"- **{BASELINE_DISPLAY_NAMES[key]}**: {_escape_reason(str(result['reason']))}"
        for key, result in sorted(unevaluated, key=lambda item: BASELINE_ORDER.index(item[0]))
    ]
    return "\n".join(lines)


def render_by_tier_table(results: dict[str, dict[str, Any]]) -> str:
    """Render one micro-F1-by-tier table per evaluated baseline."""
    evaluated = [
        key for key in BASELINE_ORDER if key in results and results[key]["status"] == "evaluated"
    ]
    if not evaluated:
        return "No evaluated baselines yet."
    header = "| System | " + " | ".join(f"{tier} (exact / overlap)" for tier in TIERS) + " |"
    separator = "|---|" + "---|" * len(TIERS)
    rows = [header, separator]
    for key in evaluated:
        by_tier = results[key]["metrics"]["by_tier"]
        cells = [BASELINE_DISPLAY_NAMES[key]]
        for tier in TIERS:
            tier_scores = by_tier[tier]
            exact_f1 = _fmt_float(tier_scores["exact_micro_f1"])
            overlap_f1 = _fmt_float(tier_scores["overlap_micro_f1"])
            cells.append(f"{exact_f1} / {overlap_f1}")
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def _first_field(results: dict[str, dict[str, Any]], *field_path: str) -> str:
    for key in BASELINE_ORDER:
        result = results.get(key)
        if result is None:
            continue
        value: object = result
        for field in field_path:
            if not isinstance(value, dict) or field not in value:
                value = None
                break
            value = value[field]
        if value is not None:
            return str(value)
    return "unknown"


METHOD_SECTION = """## Method

**Exact match**: a prediction counts as a true positive only if its
`(start, end, label)` matches a gold span exactly. This is the primary
metric throughout this document and in every result JSON.

**Overlap match**: a prediction counts as a true positive if it shares a
label with a gold span and their character ranges intersect at all, more
forgiving of boundary errors. Reported alongside exact, never in place of
it. Both use greedy one-to-one matching: each gold span can be claimed by
at most one predicted span.

**FPR (negatives)**: of the 50 negative-tier examples (number-dense
sentences with zero PII), the fraction on which a baseline predicts any
span at all, of any label.

**False entities per 1000 characters**: exact-match false positives,
summed across all 300 examples (all tiers, negatives included) and
normalized by total input length. Exact rather than overlap is used here
for the same reason it is the primary metric elsewhere: a boundary-off
prediction is already counted as a (false positive, false negative) pair
under exact, so this number does not double-penalize it under a looser
rule.

**Latency**: wall-clock time per `predict()` call, measured in-process on
the machine that ran the benchmark, after a warmup period whose
predictions are still used for scoring but excluded from the p50/p95/mean
calculation.
"""


def render_benchmark_doc(results: dict[str, dict[str, Any]]) -> str:
    """Render the full contents of docs/benchmark.md."""
    testset_sha256 = _first_field(results, "metadata", "testset_sha256")
    n_examples = _first_field(results, "metadata", "n_examples")
    hardware = _first_field(results, "metadata", "hardware")
    python_version = _first_field(results, "metadata", "python")

    sections = [
        "# zhtw-pii Benchmark (v0)",
        (
            "Every number below is rendered from `results/benchmark/v0/*.json` by "
            "`make report` (`zhtw_pii/eval/report.py`); `make report-check` fails CI "
            "if this file or README's benchmark table drifts from those JSON files. "
            "See `docs/adr/0008-results-json-is-source-of-truth.md`."
        ),
        METHOD_SECTION,
        (
            f"Test set: `data/testset/v0/test.jsonl`, {n_examples} examples, "
            f"SHA256 `{testset_sha256}`.\n\n"
            f"Measured on: {hardware}, Python {python_version}."
        ),
        "## Results",
        render_main_table(results),
        "## Unevaluated baselines",
        render_unevaluated_section(results),
        "## Results by tier (micro F1, exact / overlap)",
        render_by_tier_table(results),
        LIMITATIONS_SECTION,
    ]
    return "\n\n".join(sections).strip() + "\n"


LIMITATIONS_SECTION = """## Limitations

- **Pre-audit.** The 30-example manual audit of `data/testset/v0/test.jsonl`
  (Issue #4) has not run yet. These numbers are not yet confirmed against a
  human check of the gold labels themselves.
- **Synthetic distribution only.** Every name, address, and organization in
  the test set is generated from public statistical lexicons and
  hand-written templates (`data/DATA_CARD.md`); none of these numbers
  represent performance on real Taiwanese text.
- **Label mapping is a design choice, not a fact about the tools.** Presidio's
  `LOCATION`/`GPE` and GLiNER2's `address` are mapped onto this project's
  `ADDRESS`; Presidio's `ORGANIZATION`/`ORG` onto `ORG`. A different mapping
  would score differently. See each baseline's `config.label_mapping` in its
  result JSON.
- **GLiNER2-PII's low Chinese recall tracks sentence complexity, and is a
  script/language transfer gap, not a label-familiarity one.** Its 42
  trained PII types (`fastino/gliner2-privacy-filter-PII-multi`'s model
  card) do not include an organization/company type, yet querying it with
  "organization name" (a label it was never fine-tuned on) correctly
  extracts an organization span from English text: GLiNER's zero-shot
  label generalization holds for an unseen label. On Traditional Chinese
  input the same three-label query recovers most of its by-tier score on
  short, low-context sentences (59-60% exact micro F1 on the easy tier)
  but collapses on medium and hard (0.7-7% exact micro F1), where entities
  sit inside longer, noisier sentences; the overall 13-17% micro F1 blends
  those two regimes. Ad hoc checks on isolated inputs during development
  found the same pattern: a bare, context-free name alone can clear a very
  low threshold while an otherwise identical name embedded in a full
  sentence does not, down to threshold 0.02. Its model card's declared
  supported languages (en/fr/es/de/it/pt/nl) do not include zh; both
  label-set variants are run on Traditional Chinese text anyway, which is
  this benchmark's actual question about it, and this tier-dependent result is that
  question answered, not a bug in this adapter.
- **The regex baseline's surname list is a strict superset of the synthetic
  generator's.** `zhtw_pii/eval/baselines/lexicon/top100_surnames.txt` (100
  surnames, an independently sourced public list; see that file's header)
  contains every surname in `zhtw_pii/data/lexicon/surnames.txt` (the
  generator's 39-surname list) as a subset. The regex baseline can never miss
  a synthetic PERSON span for surname-list reasons; its errors are entirely
  from given-name boundary detection, not surname coverage. A regex
  evaluated against a differently-sourced test set would not have this
  advantage.
- **The regex baseline is a naive lower bound by design**, not a tuned
  system: no dictionary distinguishes a given name from an ordinary word, so
  it false-positives on words like "金額" (amount, because "金" is a real
  surname) and on "高雄" (Kaohsiung, because "高" is a real surname; this is
  internal/PLAN.md's own canonical example of why PERSON needs a model, not
  a regex). See the design-deviations note in
  `zhtw_pii/eval/baselines/regex_rules.py`.
- **This is not a compliance tool.** None of these numbers guarantee
  complete PII detection; see `SECURITY.md`.
"""


def render_readme_section(results: dict[str, dict[str, Any]]) -> str:
    """Render the compact table that replaces README's marked region."""
    generated_note = (
        "<!-- Generated by `make report` (zhtw_pii/eval/report.py) from "
        "results/benchmark/v0/*.json. Do not edit by hand. -->"
    )
    see_also = (
        "Full method, unevaluated-baseline reasons, and per-tier results "
        "in [docs/benchmark.md](docs/benchmark.md)."
    )
    lines = [
        README_MARKER_START,
        generated_note,
        "",
        render_main_table(results),
        "",
        see_also,
        README_MARKER_END,
    ]
    return "\n".join(lines)


def _replace_readme_section(readme_text: str, new_section: str) -> str:
    start = readme_text.find(README_MARKER_START)
    end = readme_text.find(README_MARKER_END)
    if start == -1 or end == -1:
        raise ValueError(
            f"README.md is missing {README_MARKER_START} / {README_MARKER_END}; "
            "add the markers once by hand around the Benchmark table before running report"
        )
    end += len(README_MARKER_END)
    return readme_text[:start] + new_section + readme_text[end:]


def render(results_dir: Path | None = None) -> tuple[str, str]:
    """Render both output documents. Returns (benchmark_doc_text, updated_readme_text).

    `results_dir` defaults to the module-level `RESULTS_DIR`, read at call
    time (not bound as a default argument value) so that tests can
    `monkeypatch.setattr(report, "RESULTS_DIR", ...)` and have it take
    effect through `write()` and `check()`, which call `render()` with no
    arguments.
    """
    results = load_results(results_dir if results_dir is not None else RESULTS_DIR)
    benchmark_doc = render_benchmark_doc(results)
    readme_section = render_readme_section(results)
    current_readme = README_PATH.read_text(encoding="utf-8")
    updated_readme = _replace_readme_section(current_readme, readme_section)
    return benchmark_doc, updated_readme


def write() -> None:
    """Render and write docs/benchmark.md and README.md."""
    benchmark_doc, updated_readme = render()
    BENCHMARK_DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    BENCHMARK_DOC_PATH.write_text(benchmark_doc, encoding="utf-8")
    README_PATH.write_text(updated_readme, encoding="utf-8")


def check() -> int:
    """Re-render in memory and diff against disk. Returns the process exit code."""
    benchmark_doc, updated_readme = render()
    exit_code = 0
    on_disk_benchmark_doc = (
        BENCHMARK_DOC_PATH.read_text(encoding="utf-8") if BENCHMARK_DOC_PATH.exists() else ""
    )
    if on_disk_benchmark_doc != benchmark_doc:
        exit_code = 1
        print(f"{BENCHMARK_DOC_PATH} is stale relative to results/*.json:", file=sys.stderr)
        _print_diff(on_disk_benchmark_doc, benchmark_doc, str(BENCHMARK_DOC_PATH))
    on_disk_readme = README_PATH.read_text(encoding="utf-8")
    if on_disk_readme != updated_readme:
        exit_code = 1
        print(f"{README_PATH} benchmark table is stale relative to results:", file=sys.stderr)
        _print_diff(on_disk_readme, updated_readme, str(README_PATH))
    if exit_code == 0:
        print("docs/benchmark.md and README.md are up to date with results/benchmark/v0/*.json")
    return exit_code


def _print_diff(old_text: str, new_text: str, label: str) -> None:
    diff = difflib.unified_diff(
        old_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile=f"{label} (on disk)",
        tofile=f"{label} (rendered)",
    )
    sys.stderr.writelines(list(diff)[:60])


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render results/*.json into the benchmark docs.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="check that docs/benchmark.md and README.md are up to date, without writing",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Entry point for `python -m zhtw_pii.eval.report`."""
    args = build_arg_parser().parse_args(argv)
    if args.check:
        sys.exit(check())
    write()


if __name__ == "__main__":
    main()
