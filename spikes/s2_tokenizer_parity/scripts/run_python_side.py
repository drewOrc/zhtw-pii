"""Tokenize the test set and adversarial set with the Python `tokenizers` library.

Loads each tokenizer directly from its downloaded tokenizer.json (the same file
bytes the Node side loads; see scripts/download_models.py), encodes every example,
and dumps input_ids / token strings / char offsets / UNK positions to
results/raw/python_<name>.json. This is the ground truth the Node-side output and
the offset-reconstruction prototype are checked against.

Usage:
    uv run --python 3.11 --with-requirements requirements.txt python scripts/run_python_side.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tokenizers import Tokenizer

SPIKE_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = SPIKE_ROOT / "models"
RAW_DIR = SPIKE_ROOT / "results" / "raw"
REPO_ROOT = SPIKE_ROOT.parent.parent

TOKENIZER_NAMES = [
    "bert-base-chinese",
    "ckiplab-bert-tiny-chinese-ner",
    "bert-base-multilingual-cased",
    "distilbert-base-multilingual-cased",
    "xlm-roberta-base",
]


def load_examples() -> list[dict[str, Any]]:
    """Load the 300-example test set and the 38-example adversarial set."""
    examples = []
    test_path = REPO_ROOT / "data" / "testset" / "v0" / "test.jsonl"
    with test_path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            row["source"] = "test"
            examples.append(row)

    adv_path = SPIKE_ROOT / "data" / "adversarial.jsonl"
    with adv_path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            row["source"] = "adversarial"
            examples.append(row)

    return examples


def get_unk_token(tokenizer_json_path: Path) -> str:
    """Read the UNK token string directly out of tokenizer.json.

    WordPiece models store it at model.unk_token. Unigram (SentencePiece)
    models store model.unk_id, an index into model.vocab.
    """
    data = json.loads(tokenizer_json_path.read_text())
    model = data["model"]
    if model.get("unk_token"):
        return model["unk_token"]
    if model.get("unk_id") is not None:
        return model["vocab"][model["unk_id"]][0]
    raise ValueError(f"cannot determine unk token from {tokenizer_json_path}")


def encode_example(tok: Tokenizer, unk_token: str, text: str) -> dict[str, Any]:
    """Encode one text and collect everything needed for downstream comparison."""
    encoding = tok.encode(text)
    unk_char_spans = [
        {"start": s, "end": e, "text": text[s:e]}
        for token_str, (s, e) in zip(encoding.tokens, encoding.offsets, strict=True)
        if token_str == unk_token
    ]
    content_tokens = [
        t for t, m in zip(encoding.tokens, encoding.special_tokens_mask, strict=True) if m == 0
    ]
    return {
        "input_ids": encoding.ids,
        "tokens": encoding.tokens,
        "offsets": [list(pair) for pair in encoding.offsets],
        "special_tokens_mask": encoding.special_tokens_mask,
        "content_tokens": content_tokens,
        "num_ids": len(encoding.ids),
        "unk_char_spans": unk_char_spans,
    }


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    examples = load_examples()
    print(f"loaded {len(examples)} examples (test + adversarial)")

    for name in TOKENIZER_NAMES:
        tokenizer_json_path = MODELS_DIR / name / "tokenizer.json"
        tok = Tokenizer.from_file(str(tokenizer_json_path))
        unk_token = get_unk_token(tokenizer_json_path)

        results = []
        for ex in examples:
            encoded = encode_example(tok, unk_token, ex["text"])
            results.append(
                {
                    "id": ex["id"],
                    "source": ex["source"],
                    "tier": ex["tier"],
                    "text": ex["text"],
                    "text_len_chars": len(ex["text"]),
                    "entities": ex.get("entities", []),
                    **encoded,
                }
            )

        out_path = RAW_DIR / f"python_{name}.json"
        out_path.write_text(json.dumps(results, ensure_ascii=False))
        num_unk = sum(len(r["unk_char_spans"]) for r in results)
        max_ids = max(r["num_ids"] for r in results)
        print(
            f"{name}: unk_token={unk_token!r} "
            f"unk_spans={num_unk} max_ids={max_ids} -> {out_path.relative_to(SPIKE_ROOT)}"
        )


if __name__ == "__main__":
    main()
