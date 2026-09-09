"""Prototype: recover character-level spans from token strings alone.

transformers.js does not expose offset_mapping (see RESULTS.md). A browser NER
demo therefore needs some way to turn token-level predictions back into
character spans in the original text using only token strings and the text
itself. This script implements a greedy forward-search reconstruction and
scores it against the Python tokenizers library's real `encoding.offsets`,
run once on the Python-side token list (upper bound: tokens are guaranteed
correct) and once on the Node-side token list (the real M2 scenario).

Algorithm (WordPiece and SentencePiece-Unigram, driven by strings only):
  - Strip the continuation/word-start marker from a token ("##foo" -> "foo",
    "_foo" (U+2581) -> "foo") to get its surface form.
  - Search for that surface form starting at the current cursor, case-matched
    as-is (all 5 tokenizers under test are cased: do_lower_case=false), within
    a bounded lookahead window first (cheap, and correct for the common case
    where the next token sits right after the cursor); fall back to an
    unbounded forward search if the bounded window misses.
  - [UNK] / <unk> tokens carry no surface form to search for. Traditional
    Chinese text is tokenize_chinese_chars-split so an unresolved character is
    overwhelmingly a single code point; consume exactly one character. This is
    a known simplification -- see RESULTS.md Limitations for when it
    under/over-consumes (runs of >1 consecutive unknown characters).
  - Advance the cursor to the end of each resolved span.

Usage:
    uv run --python 3.11 --with-requirements requirements.txt python scripts/reconstruct_offsets.py
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any

SPIKE_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = SPIKE_ROOT / "results" / "raw"

TOKENIZER_NAMES = [
    "bert-base-chinese",
    "ckiplab-bert-tiny-chinese-ner",
    "bert-base-multilingual-cased",
    "distilbert-base-multilingual-cased",
    "xlm-roberta-base",
]

UNK_TOKENS = {"[UNK]", "<unk>"}
SENTENCEPIECE_WORD_START = "▁"  # '▁'


def strip_marker(token: str) -> str:
    """Remove a WordPiece '##' continuation marker or SentencePiece '▁' word-start marker."""
    if token.startswith("##"):
        return token[2:]
    if token.startswith(SENTENCEPIECE_WORD_START):
        return token[len(SENTENCEPIECE_WORD_START) :]
    return token


def _find_piece(text: str, piece: str, cursor: int) -> int:
    """Search for `piece` starting at `cursor`: a bounded window first (cheap,
    correct for the common back-to-back case), then an unbounded fallback."""
    n = len(text)
    window_end = min(n, cursor + len(piece) + 32)
    idx = text.find(piece, cursor, window_end)
    if idx == -1:
        idx = text.find(piece, cursor)
    return idx


def reconstruct_spans(text: str, tokens: list[str]) -> list[tuple[int, int] | None]:
    """Greedily align a flat token-string list back onto `text`, returning one
    (start, end) char span per token, or None where alignment failed.

    Matches token surface forms literally against `text`. This is the naive
    variant: it has no notion of what the tokenizer's own normalizer did to
    the text before tokenizing, so it fails whenever a token's surface form
    is not a literal substring of `text` (see the NFKC-aware variant below).

    UNK handling: a WordPiece/Unigram [UNK] token can swallow a run of
    several consecutive untokenizable characters, not just one (e.g. a run of
    fullwidth digits absent from a Chinese-focused vocab). This looks ahead to
    the next resolvable token and, if found nearby, attributes the whole gap
    up to that match to the UNK token, instead of guessing a fixed width.
    """
    cursor = 0
    n = len(text)
    spans: list[tuple[int, int] | None] = []

    for i, tok in enumerate(tokens):
        if tok in UNK_TOKENS:
            next_start = None
            for lookahead in tokens[i + 1 : i + 3]:
                if lookahead in UNK_TOKENS:
                    break
                piece = strip_marker(lookahead)
                if not piece:
                    continue
                idx = _find_piece(text, piece, cursor)
                if idx != -1:
                    next_start = idx
                break
            end = (
                next_start if next_start is not None and next_start > cursor else min(cursor + 1, n)
            )
            spans.append((cursor, end))
            cursor = end
            continue

        piece = strip_marker(tok)
        if not piece:
            spans.append((cursor, cursor))
            continue

        idx = _find_piece(text, piece, cursor)
        if idx == -1:
            spans.append(None)
            cursor = n
            continue

        start, end = idx, idx + len(piece)
        spans.append((start, end))
        cursor = end

    return spans


def reconstruct_spans_nfkc_aware(
    text: str, tokens: list[str]
) -> list[tuple[int, int] | None] | None:
    """Like reconstruct_spans, but matches against the NFKC-normalized text.

    xlm-roberta-base's SentencePiece model ships a "Precompiled" normalizer
    (a precompiled charsmap), which empirically folds fullwidth-forms
    (U+FF00-FFEF, e.g. '：' -> ':') the same way NFKC does (verified against
    Python's unicodedata.normalize) before tokenizing. The naive matcher above
    can't see through that: it searches for the post-fold piece in the
    pre-fold original text and fails. This variant normalizes the text first
    so pieces match, then relies on NFKC being length-preserving for the
    fullwidth-forms fold specifically (verified for this project's adversarial
    set) to reuse the resulting indices directly against the original text.
    Returns None if NFKC changes the text's length (can't safely map back;
    caller should fall back to the naive variant and flag it as unresolved).
    """
    nfkc_text = unicodedata.normalize("NFKC", text)
    if len(nfkc_text) != len(text):
        return None
    return reconstruct_spans(nfkc_text, tokens)


def _nfkc_aware_with_fallback(text: str, tokens: list[str]) -> list[tuple[int, int] | None]:
    result = reconstruct_spans_nfkc_aware(text, tokens)
    return result if result is not None else reconstruct_spans(text, tokens)


def score_against_ground_truth(
    examples: list[dict[str, Any]],
    side_tokens_key: str,
    reconstructor=reconstruct_spans,
) -> dict[str, Any]:
    """Run reconstruction on `side_tokens_key` tokens and score against Python offsets.

    `examples` is the Python-side raw dump (has true content-token offsets via
    special_tokens_mask). When side_tokens_key points at Node's token list, the
    example is matched by id from the Node raw dump before calling this.
    """
    token_total = 0
    token_correct = 0
    excluded_length_mismatch = 0
    mismatched_examples: list[dict[str, Any]] = []

    entity_total = 0
    entity_correct = 0
    entity_mismatches: list[dict[str, Any]] = []

    for ex in examples:
        true_content_offsets = [
            tuple(off)
            for off, m in zip(ex["offsets"], ex["special_tokens_mask"], strict=True)
            if m == 0
        ]
        side_tokens = ex[side_tokens_key]

        if len(side_tokens) != len(true_content_offsets):
            excluded_length_mismatch += 1
            continue

        reconstructed = reconstructor(ex["text"], side_tokens)

        for recon, true_off in zip(reconstructed, true_content_offsets, strict=True):
            token_total += 1
            if recon is not None and tuple(recon) == true_off:
                token_correct += 1
            elif len(mismatched_examples) < 20:
                mismatched_examples.append(
                    {
                        "id": ex["id"],
                        "text": ex["text"],
                        "reconstructed": recon,
                        "true_offset": true_off,
                    }
                )

        for entity in ex["entities"]:
            e_start, e_end = entity["start"], entity["end"]
            covering = [
                i
                for i, off in enumerate(true_content_offsets)
                if off[0] < e_end and off[1] > e_start
            ]
            if not covering:
                continue
            entity_total += 1
            first_i, last_i = covering[0], covering[-1]
            recon_first, recon_last = reconstructed[first_i], reconstructed[last_i]
            if recon_first is None or recon_last is None:
                if len(entity_mismatches) < 20:
                    entity_mismatches.append(
                        {
                            "id": ex["id"],
                            "text": ex["text"],
                            "entity": entity,
                            "reconstructed": None,
                        }
                    )
                continue
            recon_span = (recon_first[0], recon_last[1])
            if recon_span == (e_start, e_end):
                entity_correct += 1
            elif len(entity_mismatches) < 20:
                entity_mismatches.append(
                    {
                        "id": ex["id"],
                        "text": ex["text"],
                        "entity": entity,
                        "reconstructed": list(recon_span),
                    }
                )

    return {
        "token_level": {
            "total": token_total,
            "correct": token_correct,
            "accuracy": token_correct / token_total if token_total else None,
            "excluded_length_mismatch": excluded_length_mismatch,
            "mismatch_examples": mismatched_examples,
        },
        "entity_level": {
            "total": entity_total,
            "correct": entity_correct,
            "accuracy": entity_correct / entity_total if entity_total else None,
            "mismatch_examples": entity_mismatches,
        },
    }


def main() -> None:
    all_results = {}
    for name in TOKENIZER_NAMES:
        python_examples = json.loads((RAW_DIR / f"python_{name}.json").read_text())
        node_examples = {
            e["id"]: e for e in json.loads((RAW_DIR / f"node_{name}.json").read_text())
        }

        merged = []
        for ex in python_examples:
            node_ex = node_examples.get(ex["id"])
            merged.append(
                {
                    **ex,
                    "node_content_tokens": node_ex["content_tokens"] if node_ex else [],
                }
            )

        by_source = {
            "test": [e for e in merged if e["source"] == "test"],
            "adversarial": [e for e in merged if e["source"] == "adversarial"],
            "combined": merged,
        }

        all_results[name] = {}
        for source_name, subset in by_source.items():
            python_side_score = score_against_ground_truth(subset, "content_tokens")
            node_side_score = score_against_ground_truth(subset, "node_content_tokens")
            all_results[name][source_name] = {
                "reconstruction_from_python_tokens": python_side_score,
                "reconstruction_from_node_tokens": node_side_score,
            }
            py_tok = python_side_score["token_level"]["accuracy"]
            node_tok = node_side_score["token_level"]["accuracy"]
            py_ent = python_side_score["entity_level"]["accuracy"]
            node_ent = node_side_score["entity_level"]["accuracy"]
            print(
                f"{name} [{source_name}]: "
                f"token-level py={py_tok:.4f} node={node_tok:.4f} | "
                f"entity-level py={py_ent:.4f} node={node_ent:.4f}"
            )

            # xlm-roberta-base's SentencePiece normalizer folds fullwidth-forms
            # before tokenizing (see reconstruct_spans_nfkc_aware docstring);
            # rerun with the NFKC-aware matcher so the report can show the
            # naive vs. normalization-aware gap concretely instead of just
            # asserting it.
            if name == "xlm-roberta-base":
                python_side_nfkc = score_against_ground_truth(
                    subset, "content_tokens", reconstructor=_nfkc_aware_with_fallback
                )
                node_side_nfkc = score_against_ground_truth(
                    subset, "node_content_tokens", reconstructor=_nfkc_aware_with_fallback
                )
                all_results[name][source_name]["reconstruction_from_python_tokens_nfkc_aware"] = (
                    python_side_nfkc
                )
                all_results[name][source_name]["reconstruction_from_node_tokens_nfkc_aware"] = (
                    node_side_nfkc
                )
                print(
                    f"  nfkc-aware: token-level (from python tokens)="
                    f"{python_side_nfkc['token_level']['accuracy']:.4f} "
                    f"(from node tokens)={node_side_nfkc['token_level']['accuracy']:.4f} | "
                    f"entity-level (from python tokens)="
                    f"{python_side_nfkc['entity_level']['accuracy']:.4f} "
                    f"(from node tokens)={node_side_nfkc['entity_level']['accuracy']:.4f}"
                )

    out_path = RAW_DIR / "reconstruction_scores.json"
    out_path.write_text(json.dumps(all_results, ensure_ascii=False, indent=2))
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
