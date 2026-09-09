"""Cross-check: does transformers.AutoTokenizer (the Python wrapper class,
reading tokenizer_config.json for do_lower_case / tokenize_chinese_chars /
strip_accents) apply the same normalization as loading tokenizer.json directly
with the `tokenizers` library (scripts/run_python_side.py's approach)?

This only matters for the parity claim if the two loading paths could
silently diverge: e.g. tokenizer_config.json says do_lower_case=true but the
tokenizer.json's embedded BertNormalizer says lowercase=false (or vice versa),
which would mean the "same tokenizer.json bytes" premise is not sufficient by
itself and the wrapping class also matters.

Runs without torch (see requirements.txt).

Usage:
    uv run --python 3.11 --with-requirements requirements.txt python \
        scripts/cross_check_transformers.py
"""

from __future__ import annotations

import json
from pathlib import Path

from tokenizers import Tokenizer
from transformers import AutoTokenizer

SPIKE_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = SPIKE_ROOT / "models"

TOKENIZER_NAMES = [
    "bert-base-chinese",
    "ckiplab-bert-tiny-chinese-ner",
    "bert-base-multilingual-cased",
    "distilbert-base-multilingual-cased",
    "xlm-roberta-base",
]

PROBE_TEXTS = [
    "王先生的地址是台北市信義區。",
    "客戶編號：ABC－１２３４５６。",
    "Kevin Wu 與陳怡君 will follow up.",
    "café Müller",  # accented Latin; BertNormalizer here has strip_accents=None, lowercase=False
    "MIXED case ENGLISH text",
]


def main() -> None:
    report = {}
    all_match = True

    for name in TOKENIZER_NAMES:
        local_dir = MODELS_DIR / name
        raw_tok = Tokenizer.from_file(str(local_dir / "tokenizer.json"))
        # local_files_only avoids any network fallback; use_fast=True is the
        # default for AutoTokenizer but stated explicitly since the whole
        # point of this check is the fast-tokenizer wrapper's behavior.
        auto_tok = AutoTokenizer.from_pretrained(
            str(local_dir), use_fast=True, local_files_only=True
        )

        mismatches = []
        for text in PROBE_TEXTS:
            raw_ids = raw_tok.encode(text).ids
            auto_ids = auto_tok(text)["input_ids"]
            if raw_ids != auto_ids:
                mismatches.append(
                    {"text": text, "raw_tokenizers_ids": raw_ids, "auto_tokenizer_ids": auto_ids}
                )

        report[name] = {
            "auto_tokenizer_class": type(auto_tok).__name__,
            "probes_checked": len(PROBE_TEXTS),
            "mismatches": mismatches,
            "all_probes_match": len(mismatches) == 0,
        }
        if mismatches:
            all_match = False
        print(
            f"{name}: {type(auto_tok).__name__}, "
            f"{'all probes match' if not mismatches else f'{len(mismatches)} MISMATCHES'}"
        )

    out_path = SPIKE_ROOT / "results" / "raw" / "cross_check_transformers.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nall tokenizers' AutoTokenizer wrapper matches raw tokenizers.Tokenizer: {all_match}")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
