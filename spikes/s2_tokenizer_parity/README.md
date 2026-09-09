# S2: zh-TW tokenizer parity spike

GitHub issue #2. Does `@huggingface/transformers` (transformers.js) tokenize Traditional
Chinese text identically to Python's `tokenizers` library, for the same `tokenizer.json`?
Findings, tables, and the recommendation for M2 are in [`RESULTS.md`](RESULTS.md). This
file is rerun steps only.

This spike is self-contained: its own `requirements.txt` and `package.json` (both pinned
to exact versions), independent of the root project's `pyproject.toml` / `uv.lock`. It is
excluded from the root lint/test config on purpose (see `spikes/README.md`).

## Prerequisites

- `uv` (any recent version; resolves and runs Python 3.11 itself, no separate install needed)
- Node.js and npm (tested with Node v24.13.1 / npm 11.8.0; any reasonably current Node 20+
  should work, but the exact numbers above are what this spike's results were produced with)
- Network access to huggingface.co (downloads ~12 MB of tokenizer files across 5 repos;
  see the size note below)

## Rerun steps

From this directory (`spikes/s2_tokenizer_parity/`):

```bash
# 1. Download tokenizer.json + small config files for all 5 tokenizers into models/
#    (gitignored; ~12 MB total, dominated by xlm-roberta-base's ~9 MB SentencePiece vocab).
#    Revisions are pinned to a specific commit SHA per repo, so this downloads the same
#    bytes RESULTS.md describes even if the upstream repos change later.
uv run --python 3.11 --with-requirements requirements.txt python scripts/download_models.py

# 2. Tokenize the test set (data/testset/v0/test.jsonl, 300 examples) and the adversarial
#    set (data/adversarial.jsonl, 38 examples) with Python's `tokenizers` library.
#    Writes results/raw/python_<name>.json (gitignored intermediate).
uv run --python 3.11 --with-requirements requirements.txt python scripts/run_python_side.py

# 3. Install the Node side (writes node_modules/, gitignored) and tokenize the same
#    examples with transformers.js. Writes results/raw/node_<name>.json.
npm install
node scripts/run_node_side.mjs

# 4. Score the offset-reconstruction prototype against the Python tokenizers library's
#    real encoding.offsets, using both Python's and Node's token lists.
#    Writes results/raw/reconstruction_scores.json.
uv run --python 3.11 --with-requirements requirements.txt python scripts/reconstruct_offsets.py

# 5. Cross-check: does transformers.AutoTokenizer (reads tokenizer_config.json's
#    do_lower_case / tokenize_chinese_chars / strip_accents) match loading tokenizer.json
#    directly? Runs without torch. Writes results/raw/cross_check_transformers.json.
uv run --python 3.11 --with-requirements requirements.txt python scripts/cross_check_transformers.py

# 6. Combine everything into the single committed results file.
uv run --python 3.11 --with-requirements requirements.txt python scripts/compare_and_report.py
```

Step 6 writes `results/s2_results.json` (committed) and prints a one-line summary per
tokenizer. Steps 1-5 write to `models/` and `results/raw/`, both gitignored: they are
reproducible intermediates, not source of truth.

## What gets downloaded

`scripts/download_models.py` fetches only `tokenizer.json`, `tokenizer_config.json`,
`special_tokens_map.json`, `config.json`, and `vocab.txt` (when present) for each of 5
repos: no model weights (`.bin` / `.safetensors` / `.onnx`) are ever downloaded, since this
spike compares tokenization only. `ckiplab/bert-tiny-chinese-ner` has no `tokenizer.json`
of its own; the script verifies its `vocab.txt` is byte-identical to `bert-base-chinese`'s
before reusing that file (see RESULTS.md for why this is safe, not an assumption).

## Verifying nothing heavy got tracked

Before pushing, from the repo root:

```bash
git ls-files | grep -E 'models/|node_modules|\.venv|tokenizer\.json$'
```

Expected output: empty. `models/`, `node_modules/`, and `results/raw/` are all gitignored
(see `.gitignore` in this directory); only `data/adversarial.jsonl`, `results/s2_results.json`,
the scripts, `package.json` / `package-lock.json` / `requirements.txt`, this file, and
`RESULTS.md` are committed.
