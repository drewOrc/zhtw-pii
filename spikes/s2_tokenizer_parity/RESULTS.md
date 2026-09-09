# S2: zh-TW tokenizer parity between Python and transformers.js

Spike for GitHub issue #2. Time-boxed to one evening. Full raw data and metadata:
[`results/s2_results.json`](results/s2_results.json). Rerun steps: [`README.md`](README.md).

## Method

For each of 5 candidate tokenizers, the exact same `tokenizer.json` file (verified by
SHA256) is loaded on both sides: Python's `tokenizers.Tokenizer.from_file()` and Node's
`@huggingface/transformers` `AutoTokenizer.from_pretrained()` pointed at a local model
directory. Both sides tokenize the same 338 examples (the project's 300-example
`data/testset/v0/test.jsonl` plus a 38-example hand-authored adversarial set covering
fullwidth digits/punctuation, halfwidth-mixed text, English mixed in, emoji, rare
Traditional Chinese characters, multiple consecutive spaces, newlines, honorific forms,
and three deliberately long sentences to probe the 512-token ceiling) and the outputs are
diffed.

Exact commands (also in `README.md`):

```bash
uv run --python 3.11 --with-requirements requirements.txt python scripts/download_models.py
uv run --python 3.11 --with-requirements requirements.txt python scripts/run_python_side.py
npm install
node scripts/run_node_side.mjs
uv run --python 3.11 --with-requirements requirements.txt python scripts/reconstruct_offsets.py
uv run --python 3.11 --with-requirements requirements.txt python scripts/cross_check_transformers.py
uv run --python 3.11 --with-requirements requirements.txt python scripts/compare_and_report.py
```

Versions: Node v24.13.1, npm 11.8.0, Python 3.11.14, `@huggingface/transformers` 4.2.0,
`tokenizers` 0.23.2, `huggingface_hub` 1.30.0, `transformers` 5.16.1 (cross-check only, no
torch). Full metadata including per-tokenizer HF repo id, pinned commit SHA, and
`tokenizer.json` SHA256 is in `results/s2_results.json:metadata`.

### Tokenizers under test

| Local name | HF repo actually used | Family | Note |
|---|---|---|---|
| `bert-base-chinese` | `bert-base-chinese` (resolves to `google-bert/bert-base-chinese`) | WordPiece, ~21k vocab | Has its own `tokenizer.json` |
| `ckiplab-bert-tiny-chinese-ner` | `ckiplab/bert-tiny-chinese-ner`, **tokenizer.json reused from `bert-base-chinese`** | WordPiece, ~21k vocab | See below |
| `bert-base-multilingual-cased` | `bert-base-multilingual-cased` (`google-bert/...`) | WordPiece, ~119k vocab | Has its own `tokenizer.json` |
| `distilbert-base-multilingual-cased` | `distilbert-base-multilingual-cased` (`distilbert/...`) | WordPiece, ~119k vocab | Has its own `tokenizer.json` |
| `xlm-roberta-base` | `xlm-roberta-base` (`FacebookAI/...`) | SentencePiece Unigram, ~250k vocab | Has its own `tokenizer.json` |

**`ckiplab/bert-tiny-chinese-ner` ships no `tokenizer.json`** (slow-tokenizer repo: only
`vocab.txt` + `tokenizer_config.json` + `special_tokens_map.json`). Rather than guess at a
third-party mirror, `scripts/download_models.py` verified its `vocab.txt` is byte-identical
to `bert-base-chinese`'s (SHA256 `45bbac6b...c27b291c` on both sides) and that its
`tokenizer_config.json` literally declares `"name_or_path": "bert-base-chinese"` with
matching normalization flags (`do_lower_case: false`, `tokenize_chinese_chars: true`).
Given that, this spike reuses `bert-base-chinese`'s `tokenizer.json` for the ckiplab row,
which is why their results are identical throughout this document. This is recorded, not
silent: see `results/s2_results.json` -> `metadata.tokenizers_under_test.ckiplab-bert-tiny-chinese-ner`.

**Incidental finding**: `bert-base-multilingual-cased` and `distilbert-base-multilingual-cased`
also ship byte-identical `tokenizer.json` files (same SHA256, `f4a4d5bf...ec229f386`);
distillation kept the exact same WordPiece vocabulary, so their rows below are identical too.

## Result 1: input_ids parity

**Perfect parity. 0 mismatches across all 5 tokenizers, 338/338 examples each (1,690
comparisons total).**

| Tokenizer | Test set (300) | Adversarial (38) | Combined |
|---|---|---|---|
| bert-base-chinese | 300/300 (100.00%) | 38/38 (100.00%) | 100.00% |
| ckiplab-bert-tiny-chinese-ner | 300/300 (100.00%) | 38/38 (100.00%) | 100.00% |
| bert-base-multilingual-cased | 300/300 (100.00%) | 38/38 (100.00%) | 100.00% |
| distilbert-base-multilingual-cased | 300/300 (100.00%) | 38/38 (100.00%) | 100.00% |
| xlm-roberta-base | 300/300 (100.00%) | 38/38 (100.00%) | 100.00% |

This directly answers the issue's core question: when transformers.js and the Python
`tokenizers` library load the same `tokenizer.json` bytes, they produce byte-for-byte
identical `input_ids` for Traditional Chinese text, including every adversarial category
(fullwidth forms, emoji, rare characters, mixed-width punctuation, honorifics, multi-space,
newlines, >512-token sentences). No mismatch examples exist to show.

## Result 2: token counts and the 512 ceiling

| Tokenizer | Test set mean | Test set p95 | Test set max | Adversarial max | Adversarial examples > 512 |
|---|---|---|---|---|---|
| bert-base-chinese | 25.5 | 40 | 45 | 1402 | 3 (`adv_long_01/02/03`) |
| ckiplab-bert-tiny-chinese-ner | 25.5 | 40 | 45 | 1402 | 3 |
| bert-base-multilingual-cased | 26.0 | 40 | 46 | 1402 | 3 |
| distilbert-base-multilingual-cased | 26.0 | 40 | 46 | 1402 | 3 |
| xlm-roberta-base | 21.2 | 32 | 35 | 1003 | 3 |

Token counts are `len(input_ids)` including `[CLS]`/`[SEP]` (or `<s>`/`</s>`) special
tokens. On the project's actual 300-example test set, sentence length is nowhere near the
512-token ceiling for any of the 5 tokenizers (max 46 tokens). The ceiling only becomes
relevant for the three deliberately long adversarial examples (built by repeating a
template phrase 50-60 times specifically to probe this), where all 5 tokenizers exceed
512 as expected, confirming the check itself works, and that normal PII-detection-length
input (single sentences, form fields) is not at risk. xlm-roberta's SentencePiece tokens
are consistently ~15-20% fewer per sentence than the WordPiece tokenizers (single Chinese
characters more often merge into 2-3 character SentencePiece units, vs. WordPiece's
near-1:1 character-to-token mapping under `tokenize_chinese_chars`).

## Result 3: UNK rate (character-level)

| Tokenizer | Test set UNK rate | Adversarial UNK rate | Test set top UNK'd strings |
|---|---|---|---|
| bert-base-chinese | 4.57% (351/7680 chars) | 1.38% (57/4124 chars) | `NT`, `Ｇ`, `C`, `Ｃ`, `F`, `Ｐ１７５２`, `ＮＴ＄３１`, `Ａ４５９７２２１６６` |
| ckiplab-bert-tiny-chinese-ner | 4.57% (351/7680 chars) | 1.38% (57/4124 chars) | (same as above; identical tokenizer.json) |
| bert-base-multilingual-cased | 1.43% (110/7680 chars) | 0.29% (12/4124 chars) | `Ｇ`, `Ｐ１７５２`, `ＮＴ＄３１`, `Ｆ８３６８９３１８５`, `ＮＴ＄７６` |
| distilbert-base-multilingual-cased | 1.43% (110/7680 chars) | 0.29% (12/4124 chars) | (same as mBERT; identical tokenizer.json) |
| xlm-roberta-base | 0.00% | 0.00% | (none) |

UNK concentrates in the test set's `negative` tier (digit-dense non-PII sentences: product
codes, order numbers, fullwidth currency amounts), not in PERSON/ADDRESS/ORG entities.
`bert-base-chinese`'s ~21k Chinese-focused vocab has the weakest Latin/digit-run coverage
(`NT`, product code fragments); mBERT's ~119k multilingual vocab covers most of the same
strings. xlm-roberta's SentencePiece has zero UNK on both sets: Unigram with byte-level
fallback cannot go out-of-vocabulary for any Unicode input, at the cost of the token-count
and reconstruction-accuracy trade-offs above and below.

## Result 4: offsets investigation

**Finding: transformers.js exposes no character offsets anywhere in its public API.**

Checked three paths, all confirmed empirically and against `@huggingface/transformers`
4.2.0 source (installed in `node_modules/`):

1. `tokenizer(text, {return_offsets_mapping: true})`: returns the same
   `{input_ids, attention_mask}` shape as without the option. No `offset_mapping` key ever
   appears. `grep -rn 'return_offsets_mapping|offset_mapping' src/` over the installed
   package returns **zero matches**: the option isn't silently ignored, it's not
   implemented anywhere in the library.
2. `tokenizer.tokenize(text)`: returns content token strings only (no ids, no offsets,
   no special tokens).
3. Its own `token-classification` pipeline (`src/pipelines/token-classification.js`) has
   the identical gap: it pushes `{entity, score, index, word}` per predicted token, with a
   literal source comment `// TODO: Add support for start and end`, and never sets them.
   Even the NER usage example in that file's own docstring returns no span, only
   `word` (the decoded token text) and `index` (token position).

This means R2's "tokenizer inconsistency" framing is more precise as two separate
questions: **(a) does tokenization itself match**: yes, perfectly (Result 1); and
**(b) can a browser demo recover character spans from token predictions**: not natively,
it needs its own reconstruction step regardless of which tokenizer family M2 picks.

### Span reconstruction prototype

`scripts/reconstruct_offsets.py` implements a greedy forward-search reconstruction: strip
each token's continuation/word-start marker (`##` for WordPiece, `▁` for SentencePiece) to
get its surface form, search for that surface form starting at a cursor into the original
text (a bounded lookahead window first, unbounded fallback second), and advance the cursor
to the end of each match. `[UNK]`/`<unk>` tokens look ahead to the next resolvable token
and consume the gap up to it (a run of untokenizable characters, e.g. a fullwidth digit
sequence, is usually swallowed by a single UNK token, not one UNK per character).

Scored against the Python `tokenizers` library's real `encoding.offsets`, run once using
Python's own token list (upper bound: are the tokens even reconstructable in principle) and
once using transformers.js's token list (the real M2 scenario: only strings survive the
Node/browser boundary, ids and text are the only other inputs).

| Tokenizer | Token-level (test set) | Entity-level (test set) | Token-level (adversarial) | Entity-level (adversarial) |
|---|---|---|---|---|
| bert-base-chinese | 100.00% | 100.00% | 99.75% | 95.74% |
| ckiplab-bert-tiny-chinese-ner | 100.00% | 100.00% | 99.75% | 95.74% |
| bert-base-multilingual-cased | 100.00% | 100.00% | 99.90% | 100.00% |
| distilbert-base-multilingual-cased | 100.00% | 100.00% | 99.90% | 100.00% |
| xlm-roberta-base (naive) | 55.31% | 69.09% | 10.09% | 57.45% |
| xlm-roberta-base (NFKC-aware) | 95.35% | 99.56% | 98.41% | 89.36% |

(Node-side and Python-side token lists gave identical reconstruction scores in every row;
this is expected given Result 1's perfect input_ids/token parity, since there is nothing
for the two sides to disagree about once tokenization itself matches.)

**Why xlm-roberta's naive score is so much lower**: its `tokenizer.json` normalizer is
`"Precompiled"` (SentencePiece's precompiled charsmap), which empirically folds
fullwidth-forms characters (`U+FF00`-`U+FFEF`, e.g. `：` -> `:`) before tokenizing;
verified by comparing against Python's `unicodedata.normalize('NFKC', text)`, which
produces the identical fold. The naive matcher searches for the post-fold token text
(`:`) inside the pre-fold original string (which contains `：`) and fails to find it. The
WordPiece family's `BertNormalizer` does not do this fold (confirmed: `strip_accents=null,
lowercase=false`, no fullwidth handling), which is the main reason its reconstruction
accuracy is near-perfect without any extra normalization awareness. Re-running the
matcher against `unicodedata.normalize('NFKC', text)` first (valid here because the fold
is length-preserving for every case in this project's data; the script falls back to the
naive matcher when NFKC changes the string's length) recovers xlm-roberta to 95-98%.

The residual ~4-5% gap even after NFKC-awareness is a single well-understood edge case:
SentencePiece always tokenizes a synthetic leading-space marker (a lone `▁` token) at the
start of every sequence. It carries no textual surface form (nothing to search for), and
the Python tokenizers library itself assigns it an offset that *overlaps* the following
real token's offset (e.g. `▁` -> `[0,1]` and the next token `姓名` -> `[0,2]` for the text
`姓名：吳詠。`): there is no span of source text this marker alone "owns" that a
surface-text matcher could discover. This affects at most one token per example and does
not touch entity boundaries in practice (entity-level NFKC-aware accuracy on the test set
is 99.56%).

The WordPiece family's own residual gap (down from ~99.3%/99.6% before adding UNK-lookahead
to ~99.9%/100% after) is almost entirely English words split into multiple subword pieces
inside the `english_mixed` adversarial category, where the matcher has no explicit
word-boundary signal, so a run of short pieces like "Ma" + "##nager" can in principle match
near a wrong nearby occurrence. This is a known limitation of any pure decode-and-search
approach for non-CJK runs, not a bug specific to Traditional Chinese text.

## Mismatch examples

None for input_ids parity (Result 1): 0 mismatches to show. The three reconstruction
mismatch categories, with representative examples, are in
`results/s2_results.json -> per_tokenizer.<name>.offset_reconstruction.<test|adversarial>.reconstruction_from_node_tokens`
(capped at 20 examples per bucket). Representative cases already discussed above:

- **xlm-roberta, fullwidth fold**: `姓名：吳詠。`, token `:` (post-fold) not found in the
  pre-fold text; naive reconstruction returns `None`, NFKC-aware reconstruction returns
  the correct `[2, 3]`.
- **bert-base-chinese, English word split**: `本案由 Project Manager 陳怡君 follow up。`,
  "Project"/"Manager" split across several WordPiece pieces with no word-boundary
  marker surviving; reconstructed span drifts by a few characters relative to the true
  `[4, 11]` / `[12, 19]`.

## Recommendation for M2

**A WordPiece / BERT-family backbone (`bert-base-chinese`, `ckiplab/bert-tiny-chinese-ner`,
`bert-base-multilingual-cased`, or `distilbert-base-multilingual-cased`) is safe to use for
the in-browser NER pipeline.** transformers.js tokenizes it byte-for-byte identically to
the Python side (100% input_ids parity, 338/338 examples across every repo tested), and
character spans can be reconstructed from token strings alone at 100% accuracy on this
project's actual 300-example test set (99.75-99.9% token-level / 95.7-100% entity-level on
deliberately adversarial input), using the greedy-forward-search-with-UNK-lookahead
algorithm prototyped in `scripts/reconstruct_offsets.py`.

`xlm-roberta-base` (SentencePiece) also tokenizes with perfect parity and has the
side-benefit of zero UNK, but its normalizer's fullwidth-forms folding means span
reconstruction needs an explicit NFKC-normalization-aware step to be usable at all (naive:
55.3% token-level on the test set; NFKC-aware: 95.3%), and even then trails the WordPiece
family's ceiling by several points. If M1's separate NER-accuracy/size evaluation ends up
favoring xlm-roberta anyway, this is a solvable gap, not a blocker: budget the extra
reconstruction work rather than treating it as parity risk.

**R2 status**: the "tokenizer inconsistency" framing in the risk register is not confirmed
for any of the 5 tokenizers tested; tokenization itself matches perfectly. A narrower,
previously undocumented risk is confirmed instead: **transformers.js provides no character
offsets at all**, for any tokenizer family. M2 needs a client-side span-reconstruction step
regardless of backbone choice; this spike's algorithm is a working starting point for a
WordPiece backbone, and the fallback described in the issue (a small FastAPI service
instead of full in-browser inference) is not needed on tokenization-parity grounds alone.

**Concrete guidance for M2's implementation:**

1. Ship the exact `tokenizer.json` used for training as the browser artifact. No need to
   also ship `tokenizer_config.json` for the offset problem specifically (the reconstruction
   algorithm only needs token strings and the original text), but `tokenizer_config.json`
   / `config.json` are still needed for `AutoTokenizer` class resolution (confirmed via the
   cross-check below), so ship them anyway.
2. Port `scripts/reconstruct_offsets.py`'s algorithm to the demo's JS post-processing step.
   For a WordPiece backbone it can be used as-is; for xlm-roberta, add the NFKC-normalize-first
   variant.
3. **Astral-character offset unit mismatch (separate finding, not fixed here, out of this
   issue's scope but relevant to M2)**: JS strings are UTF-16; Python strings are Unicode
   code points. For any text containing an astral-plane character (most emoji), the two
   disagree on what index N means: `"王先生😀的地址".length` is `8` in JS but `len(...)` is
   `7` in Python, because JS counts the emoji as two UTF-16 units
   (`"王先生😀的地址"[3]` is a broken surrogate half, not the emoji). Since `data/generate.py`
   produces entity offsets in Python's code-point indexing, any browser-side reconstruction
   done over a raw JS string's indices would silently misalign after the first astral
   character in the text. Mitigation: iterate with `Array.from(text)` (or `[...text]`) in
   JS to get a code-point array whose indices match Python's, rather than indexing the raw
   string.

### Cross-check: `tokenizers.Tokenizer.from_file()` vs. `transformers.AutoTokenizer`

`scripts/cross_check_transformers.py` loaded each local model directory with Python's
`transformers.AutoTokenizer.from_pretrained(..., use_fast=True)` (which reads
`tokenizer_config.json`'s `do_lower_case`/`tokenize_chinese_chars`/`strip_accents` flags,
unlike loading `tokenizer.json` directly) and compared `input_ids` against the raw
`tokenizers.Tokenizer.from_file()` load, across 5 probe strings per tokenizer (including
fullwidth punctuation, mixed English/Chinese, and accented Latin text) x 5 tokenizers = 25
checks.

**Result: 100% match, 0 mismatches.** `AutoTokenizer` resolved `BertTokenizer` for the 4
WordPiece repos and `XLMRobertaTokenizer` for xlm-roberta-base, entirely via `config.json`'s
`model_type` field (none of the 5 `tokenizer_config.json` files has an explicit
`tokenizer_class` key). This confirms the project's "ship one `tokenizer.json`, both runtimes
interpret it identically" plan (PLAN.md SS3.2/SS3.3) holds even when the Python side goes
through the full `transformers` wrapper class instead of the bare `tokenizers` library;
the normalization rules live entirely inside `tokenizer.json`'s own `normalizer` field
(confirmed for these tokenizers: `BertNormalizer{clean_text:true, handle_chinese_chars:true,
strip_accents:null, lowercase:false}` for the WordPiece family,
`Precompiled{...charsmap}` for xlm-roberta), not duplicated or overridden by the wrapper.

This is `transformers`-without-torch usage only (see `requirements.txt`); it loads no model
weights.

## Limitations

- **No model weights involved.** This spike compares tokenization only, never a trained
  model's predictions. Whether a real token-classification model's confidence scores are
  usable for span aggregation (as `groupEntities()` in transformers.js's own pipeline does,
  operating on decoded `word` strings, not offsets) is untested here.
- **Only 5 tokenizers, all from the WordPiece/BERT or SentencePiece/Unigram families.** A
  byte-level BPE tokenizer (e.g. RoBERTa-English-style, GPT-2-style) was not tested and
  would need its own investigation; none of the candidate backbones in PLAN.md SS3.3 use one.
- **The span-reconstruction algorithm's UNK-run heuristic is a heuristic, not a guarantee.**
  It looks ahead at most 2 tokens to bound an UNK span; a pathological run of 3+ consecutive
  UNK tokens (not observed in either the test or adversarial set: the longest actual run
  found was 2, inside `adv_english_04`'s email address) could still misattribute characters
  between them.
- **The English-word-split gap in the WordPiece family (the `english_mixed` adversarial
  category specifically) was not further chased down** given the one-evening time box; the
  test set's own entity-level accuracy is unaffected (100%) because PERSON/ADDRESS/ORG
  entities in this project's synthetic Chinese-first templates rarely straddle a
  multi-piece English word boundary the way the adversarial probes deliberately do.
- **The astral-plane offset unit mismatch (JS UTF-16 vs. Python code points) is documented
  but not fixed or even directly exercised end-to-end here**: it was noticed while
  building the emoji adversarial examples and confirmed with a standalone `node -e` check,
  not integrated into the reconstruction scoring above (all reconstruction in this spike
  runs in Python over Python-indexed text either way, using only the token *strings* that
  came from Node; see `scripts/reconstruct_offsets.py`'s docstring). A real M2 browser
  implementation, reconstructing spans natively in JS, would need to actually apply the
  `Array.from(text)` mitigation, not just know about it.
- **`npm audit` reports 4 high-severity advisories** in `@huggingface/transformers`'s
  transitive dependencies (`onnxruntime-node` -> `adm-zip`; `sharp`), both with "no fix
  available" upstream at the time of this spike. Neither is reachable from this spike's
  code path (no ONNX model is loaded, no image is processed; only the JS-native tokenizer
  path runs), but M2 will load ONNX models and should re-check this before shipping.
- **Revisions are pinned** (`results/s2_results.json -> metadata.tokenizers_under_test.*.hf_revision`),
  so a rerun months from now downloads the same tokenizer.json bytes this document
  describes, even if the upstream repos change.
