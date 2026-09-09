"""Combine the Python-side and Node-side tokenization dumps, the offset
reconstruction scores, and the AutoTokenizer cross-check into the single
committed results file: results/s2_results.json.

Usage:
    uv run --python 3.11 --with-requirements requirements.txt python scripts/compare_and_report.py
"""

from __future__ import annotations

import json
import statistics
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

SPIKE_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = SPIKE_ROOT / "results" / "raw"
MODELS_DIR = SPIKE_ROOT / "models"

TOKENIZER_NAMES = [
    "bert-base-chinese",
    "ckiplab-bert-tiny-chinese-ner",
    "bert-base-multilingual-cased",
    "distilbert-base-multilingual-cased",
    "xlm-roberta-base",
]

MAX_MODEL_INPUT_TOKENS = 512


def sh(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()


def load_raw(name: str) -> tuple[list[dict], dict[str, dict]]:
    python_examples = json.loads((RAW_DIR / f"python_{name}.json").read_text())
    node_examples = {e["id"]: e for e in json.loads((RAW_DIR / f"node_{name}.json").read_text())}
    return python_examples, node_examples


def percentile(values: list[int], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    if f == c:
        return float(s[f])
    return s[f] + (s[c] - s[f]) * (k - f)


def input_ids_parity(python_examples: list[dict], node_examples: dict[str, dict]) -> dict[str, Any]:
    by_source: dict[str, dict[str, Any]] = {
        "test": {"total": 0, "matches": 0, "mismatches": []},
        "adversarial": {"total": 0, "matches": 0, "mismatches": []},
    }
    for ex in python_examples:
        node_ex = node_examples.get(ex["id"])
        bucket = by_source[ex["source"]]
        bucket["total"] += 1
        if node_ex is None:
            bucket["mismatches"].append(
                {"id": ex["id"], "text": ex["text"], "reason": "missing from node output"}
            )
            continue
        if ex["input_ids"] == node_ex["input_ids"]:
            bucket["matches"] += 1
        else:
            bucket["mismatches"].append(
                {
                    "id": ex["id"],
                    "text": ex["text"],
                    "python_input_ids": ex["input_ids"],
                    "node_input_ids": node_ex["input_ids"],
                    "python_tokens": ex["tokens"],
                    "node_tokens": node_ex["content_tokens"],
                }
            )

    combined_total = sum(b["total"] for b in by_source.values())
    combined_matches = sum(b["matches"] for b in by_source.values())

    result = {}
    for source, bucket in by_source.items():
        result[source] = {
            "total": bucket["total"],
            "matches": bucket["matches"],
            "match_rate": bucket["matches"] / bucket["total"] if bucket["total"] else None,
            "mismatch_examples": bucket["mismatches"][:20],
            "mismatch_count": len(bucket["mismatches"]),
        }
    result["combined"] = {
        "total": combined_total,
        "matches": combined_matches,
        "match_rate": combined_matches / combined_total if combined_total else None,
    }
    return result


def token_count_stats(python_examples: list[dict]) -> dict[str, Any]:
    by_source: dict[str, list[dict]] = {"test": [], "adversarial": []}
    for ex in python_examples:
        by_source[ex["source"]].append(ex)

    out = {}
    for source, exs in by_source.items():
        counts = [e["num_ids"] for e in exs]
        chars_per_example = [e["text_len_chars"] for e in exs]
        ratios = [c / max(t, 1) for c, t in zip(counts, chars_per_example, strict=True)]
        out[source] = {
            "n_examples": len(exs),
            "num_ids_mean": statistics.mean(counts) if counts else None,
            "num_ids_p95": percentile(counts, 0.95),
            "num_ids_max": max(counts) if counts else None,
            "tokens_per_char_mean": statistics.mean(ratios) if ratios else None,
            "n_examples_exceeding_512": sum(1 for c in counts if c > MAX_MODEL_INPUT_TOKENS),
            "ids_exceeding_512_example_ids": [
                e["id"] for e in exs if e["num_ids"] > MAX_MODEL_INPUT_TOKENS
            ],
        }
    return out


def unk_rate(python_examples: list[dict]) -> dict[str, Any]:
    by_source: dict[str, list[dict]] = {"test": [], "adversarial": []}
    for ex in python_examples:
        by_source[ex["source"]].append(ex)

    out = {}
    for source, exs in by_source.items():
        total_chars = sum(e["text_len_chars"] for e in exs)
        unk_char_count = 0
        unk_chars_seen: dict[str, int] = {}
        for e in exs:
            for span in e["unk_char_spans"]:
                span_len = span["end"] - span["start"]
                unk_char_count += span_len
                unk_chars_seen[span["text"]] = unk_chars_seen.get(span["text"], 0) + 1
        out[source] = {
            "total_chars": total_chars,
            "unk_char_count": unk_char_count,
            "unk_char_rate": unk_char_count / total_chars if total_chars else None,
            "distinct_unk_strings": sorted(unk_chars_seen, key=lambda k: -unk_chars_seen[k])[:30],
        }
    return out


def main() -> None:
    node_version = sh(["node", "--version"])
    npm_version = sh(["npm", "--version"])
    # sys.executable, not `python3 --version`: the latter would report the
    # system interpreter, not the uv-managed 3.11 this script actually runs
    # under (`uv run --python 3.11 --with-requirements requirements.txt`).
    import sys

    python_version = f"Python {sys.version.split()[0]} ({sys.executable})"
    huggingface_transformers_version = json.loads((SPIKE_ROOT / "package.json").read_text())[
        "dependencies"
    ]["@huggingface/transformers"]
    requirements_text = (SPIKE_ROOT / "requirements.txt").read_text()

    import huggingface_hub
    import tokenizers
    import transformers as hf_transformers

    resolved_python_package_versions = {
        "huggingface_hub": huggingface_hub.__version__,
        "tokenizers": tokenizers.__version__,
        "transformers": hf_transformers.__version__,
    }

    download_manifest = json.loads((MODELS_DIR / "download_manifest.json").read_text())
    reconstruction_scores = json.loads((RAW_DIR / "reconstruction_scores.json").read_text())
    cross_check = json.loads((RAW_DIR / "cross_check_transformers.json").read_text())

    per_tokenizer = {}
    for name in TOKENIZER_NAMES:
        python_examples, node_examples = load_raw(name)
        per_tokenizer[name] = {
            "input_ids_parity": input_ids_parity(python_examples, node_examples),
            "token_count_stats": token_count_stats(python_examples),
            "unk_rate": unk_rate(python_examples),
            "offset_reconstruction": reconstruction_scores[name],
            "autotokenizer_cross_check": cross_check[name],
        }

    output = {
        "metadata": {
            "generated": datetime.now(UTC).isoformat(),
            "spike_date": date.today().isoformat(),
            "versions": {
                "node": node_version,
                "npm": npm_version,
                "python": python_version,
                "@huggingface/transformers": huggingface_transformers_version,
                "python_packages_resolved": resolved_python_package_versions,
                "python_requirements_txt": requirements_text,
            },
            "tokenizers_under_test": download_manifest,
            "test_set": "data/testset/v0/test.jsonl (300 examples)",
            "adversarial_set": "spikes/s2_tokenizer_parity/data/adversarial.jsonl (38 examples)",
            "offsets_api_finding": (
                "transformers.js (@huggingface/transformers 4.2.0) does not expose "
                "character offsets anywhere in its public API. Empirically, calling "
                "tokenizer(text, {return_offsets_mapping: true}) returns the same "
                "{input_ids, attention_mask} shape as without the option -- no "
                "offset_mapping key ever appears. `grep -rn "
                "'return_offsets_mapping|offset_mapping' src/` over the installed "
                "package (v4.2.0) returns zero matches: the option is not merely "
                "ignored, it is not implemented anywhere in the library. Its own "
                "token-classification pipeline has the same gap: "
                "src/pipelines/token-classification.js pushes "
                "{entity, score, index, word} per token with a literal source comment "
                "`// TODO: Add support for start and end` and never sets them, so even "
                "the NER pipeline example in that file's own docstring returns no span. "
                "Only tokenizer.tokenize(text) [content token strings, no specials] and "
                "tokenizer.encode(text) [input_ids, specials included] are available."
            ),
        },
        "per_tokenizer": per_tokenizer,
    }

    out_path = SPIKE_ROOT / "results" / "s2_results.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {out_path} ({out_path.stat().st_size / 1024:.1f} KiB)")

    print("\n=== summary ===")
    for name in TOKENIZER_NAMES:
        p = per_tokenizer[name]
        combined_parity = p["input_ids_parity"]["combined"]["match_rate"]
        test_ts = p["token_count_stats"]["test"]
        test_unk = p["unk_rate"]["test"]
        print(
            f"{name}: input_ids parity={combined_parity:.4f} | "
            f"test mean_tokens={test_ts['num_ids_mean']:.1f} p95={test_ts['num_ids_p95']:.0f} "
            f"max={test_ts['num_ids_max']} | test unk_rate={test_unk['unk_char_rate']:.4f}"
        )


if __name__ == "__main__":
    main()
