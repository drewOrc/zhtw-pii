# S1: browser model size budget

Question: how large a token-classification/embedding model can a phone browser
load in 3 seconds and run at p95 <= 100 ms, using transformers.js? This spike
measures that budget so `internal/PLAN.md` section 2.1's size thresholds are
based on a real number instead of a guess. See `RESULTS.md` for the numbers,
the recommended thresholds, and what they imply for M2 (export path viability).

Tracks GitHub issue #1.

## What this does

1. Exports `ckiplab/bert-tiny-chinese-ner` and `ckiplab/albert-tiny-chinese-ner`
   (no ONNX on the Hub) to ONNX with `optimum-cli`, then dynamically quantizes
   both to int8 with onnxruntime. The ALBERT export succeeds but turned out
   not to load in transformers.js (see RESULTS.md), so it contributes a size
   data point but not a benchmark row.
2. Downloads the fp32 and int8 ONNX weights for three pre-converted
   transformers.js-ready models (`Xenova/bert-base-chinese`,
   `Xenova/bert-base-multilingual-cased-ner-hrl`,
   `Xenova/paraphrase-MiniLM-L3-v2`), which together with the BERT-tiny
   export give four working size points spanning roughly 11 MB to 170 MB
   (int8).
3. Serves this directory over a local static HTTP server and drives headless
   Chromium through Playwright, with CDP `Network.emulateNetworkConditions`
   throttling to simulate three network conditions, measuring cold load time
   and per-sentence inference latency for each (model, network condition)
   combination. Runs in two scripts (`run_benchmark.mjs` for the four models
   known from the start, `run_benchmark_extra.mjs` for MiniLM-L3, added after
   the ALBERT failure was discovered mid-run), merged by `merge_results.mjs`.
4. Writes the raw numbers to `results/s1_results.json` and the write-up to
   `RESULTS.md`.

## Prerequisites

- Node 24, npm (used: Node v24.13.1, npm 11.8.0)
- `uv` (used: uv 0.10.2) for the Python side; no separate Python install
  needed, `uv run --python 3.11` provisions it
- Internet access (downloads models from Hugging Face Hub and npm packages)
- macOS/Linux; commands below assume a POSIX shell

None of this touches the root project's `uv.lock` or `.venv`; both sides of
this spike carry their own locked dependencies (`package.json` +
`package-lock.json`, `requirements.txt`).

## Reproduce

All commands run from `spikes/s1_browser_budget/`.

```bash
# 1. Node side: install pinned deps and the Chromium build Playwright tests with.
npm install
npx playwright install chromium

# 2. Vendor the transformers.js runtime locally, to avoid CDN variance
#    (see .gitignore; these files are not committed).
mkdir -p web/vendor
cp node_modules/@huggingface/transformers/dist/transformers.min.js web/vendor/
cp node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.asyncify.mjs web/vendor/
cp node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.asyncify.wasm web/vendor/

# 3. Python side + model prep: export the two CKIP tiny models to ONNX,
#    quantize them to int8, and download the three pre-converted Xenova
#    models (fp32 + int8 only, skipping the fp16/q4/bnb4/uint8 variants
#    those repos also carry).
uv run --python 3.11 --with-requirements requirements.txt optimum-cli export onnx \
  --model ckiplab/bert-tiny-chinese-ner --task token-classification \
  models/ckip-bert-tiny-ner-raw
uv run --python 3.11 --with-requirements requirements.txt optimum-cli export onnx \
  --model ckiplab/albert-tiny-chinese-ner --task token-classification \
  models/ckip-albert-tiny-ner-raw
uv run --python 3.11 --with-requirements requirements.txt python \
  scripts/quantize_dynamic_int8.py models/ckip-bert-tiny-ner-raw
uv run --python 3.11 --with-requirements requirements.txt python \
  scripts/quantize_dynamic_int8.py models/ckip-albert-tiny-ner-raw

# Rearrange each export into the layout transformers.js expects
# (onnx/model.onnx + onnx/model_quantized.onnx alongside the tokenizer
# files) -- see "Model directory layout" below for the exact shape.
for name in ckip-bert-tiny-ner ckip-albert-tiny-ner; do
  src="models/${name}-raw"; dst="models/${name}"
  mkdir -p "$dst/onnx"
  cp "$src"/{config.json,tokenizer.json,tokenizer_config.json,special_tokens_map.json,vocab.txt} "$dst/"
  cp "$src/model.onnx" "$dst/onnx/model.onnx"
  cp "$src/model_quantized.onnx" "$dst/onnx/model_quantized.onnx"
  rm -rf "$src"
done

uv run --python 3.11 --with-requirements requirements.txt python scripts/download_models.py

# 4. Run the two benchmark passes (roughly 25-35 minutes combined; each
#    prints progress per model/network condition as it goes -- most of that
#    time is the mobile-fast3g condition on the two largest models and on
#    the two models given the tiny-tier's full 3-rep treatment, see
#    RESULTS.md Methodology for exactly which conditions get how many
#    reps and why).
node scripts/run_benchmark.mjs        # ckip-bert-tiny-ner, ckip-albert-tiny-ner (fails fast), xenova-bert-base-chinese, xenova-mbert-ner-hrl
node scripts/run_benchmark_extra.mjs  # xenova-paraphrase-minilm-l3

# 5. Merge both passes into one results file.
node scripts/merge_results.mjs

# Output: results/s1_results.json (raw + summarized numbers for all five
# models, with a metadata block recording exact tool/library versions,
# hardware, and the CDP network-condition parameters used).
```

`scripts/run_bert_tiny_fast3g_fixup.mjs` and `scripts/run_minilm_fast3g_fixup.mjs`
are not part of this reproduce path: they exist because the first run of
this spike used a `mobile-fast3g` timeout too short to account for the WASM
runtime download (see RESULTS.md, "A timeout that needed correcting
mid-run"), and were used to re-measure just the two affected cells
afterward. Both `run_benchmark.mjs` and `run_benchmark_extra.mjs` already
carry the corrected timeout, so a fresh reproduction does not need them; they
are kept for the historical record and because `merge_results.mjs` accepts
their output format if you ever need to re-run just one cell.

## Model directory layout

`env.localModelPath` is set to `/models/` in `web/index.html`; transformers.js
expects, for a local model directory named `<name>`:

```
models/<name>/
  config.json
  tokenizer.json
  tokenizer_config.json
  special_tokens_map.json
  vocab.txt
  onnx/
    model.onnx             (fp32, dtype: "fp32")
    model_quantized.onnx   (int8, dtype: "q8")
```

## Files

- `requirements.txt` -- pinned Python deps for the export/quantize/download
  scripts. `transformers==4.57.6` (not the current PyPI latest, 5.16.1) and
  `optimum==2.1.0` (not 2.3.0) are pinned specifically because
  `optimum-onnx==0.1.0` requires `transformers<4.58.0` and `optimum~=2.1.0`;
  see RESULTS.md for how this was discovered.
- `package.json` / `package-lock.json` -- pinned Node deps (`playwright`,
  `@huggingface/transformers`).
- `scripts/quantize_dynamic_int8.py` -- dynamic int8 quantization via
  `onnxruntime.quantization.quantize_dynamic`.
- `scripts/download_models.py` -- selective download (fp32 + int8 ONNX only)
  of the three pre-converted Xenova models via `huggingface_hub`.
- `scripts/run_benchmark.mjs` -- Playwright + CDP orchestration for the four
  models known from the start; static file server, network emulation,
  per-model/condition run matrix, JSON output.
- `scripts/run_benchmark_extra.mjs` -- same methodology, for
  `xenova-paraphrase-minilm-l3` (added after `ckip-albert-tiny-ner` turned
  out unsupported).
- `scripts/merge_results.mjs` -- combines the two runs above (and, if
  present, the two fixup scripts' output) into one `results/s1_results.json`.
- `scripts/run_bert_tiny_fast3g_fixup.mjs`,
  `scripts/run_minilm_fast3g_fixup.mjs` -- historical, not part of the
  reproduce path; see the note above the Reproduce commands.
- `web/index.html` -- the page under test; exposes `window.runBenchmark(cfg)`
  for Playwright to call via `page.evaluate`.
- `results/s1_results.json` -- raw output for all five models (metadata +
  every individual run, timed-out attempts included + computed
  medians/p50/p95).
- `results/run_log_*.txt` -- stdout/stderr of each benchmark run, one file
  per script invocation.
- `RESULTS.md` -- write-up: methodology, tables, recommended thresholds for
  `internal/PLAN.md` section 2.1, implications for M2, limitations.

## Not committed (regenerate, do not expect them in git)

- `models/` -- model weights (root `.gitignore` already blocks `*.onnx`; this
  spike's own `.gitignore` also blocks the directory itself)
- `node_modules/`
- `web/vendor/` -- copied from `node_modules/` per step 2 above
