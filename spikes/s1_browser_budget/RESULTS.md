# S1 results: browser model size budget

Tracks GitHub issue #1. Feeds the size thresholds in `internal/PLAN.md`
section 2.1 and the M1 path decision (train / distill / stop).

## TL;DR

- **The WASM runtime, not the model, is the binding constraint on mobile.**
  transformers.js's default ONNX Runtime Web build is 22.48 MiB and is
  fetched fresh on every cold visit; on `mobile-4g` (10 Mbps) that alone
  costs ~18 s, before any model bytes. A literal "3 seconds on throttled
  mobile" is not achievable at any model size tested.
- **On WiFi/desktop bandwidth, every model tested loads in under 1 second**
  locally and single-digit seconds from the real HF Hub CDN -- PLAN.md's "3
  second" bar holds fine there.
- **Recommendation: revise PLAN.md section 2.1's size threshold down to
  roughly 15 MiB int8** if a ~30 s first-visit budget on 4G matters, and
  drop `mobile-fast3g` as a gating condition entirely -- it fails for every
  size tested, by minutes, not seconds.
- **`ckiplab/bert-tiny-chinese-ner` exports and runs end to end**
  (optimum-cli -> onnxruntime quantize -> transformers.js `pipeline()`, no
  issues) at 11.11 MiB int8. **`ckiplab/albert-tiny-chinese-ner` exports
  successfully but transformers.js 4.2.0 refuses to load it**
  (`Error: Unsupported model type: albert`) -- export works, the browser
  runtime does not, worth rechecking at M2 time.
- Five size points measured end to end (int8): 8.44 MiB (ALBERT, export only,
  not loadable), 11.11 MiB, 16.64 MiB, 98.80 MiB, 170.23 MiB. See Results for
  the full table and Recommended thresholds for the PLAN.md-facing numbers.

## Methodology

### Network conditions

Measured with headless Chromium (Playwright 1.63.0, Chrome for Testing
153.0.8010.12) via CDP `Network.emulateNetworkConditions`. Exact parameters:

| Condition | Download | Upload | RTT | CDP `downloadThroughput` (bytes/s) |
|---|---|---|---|---|
| `desktop-unthrottled` | not throttled | not throttled | not throttled | n/a -- `emulateNetworkConditions` is not called for this condition |
| `mobile-4g` | 10 Mbps | 5 Mbps | 40 ms | 1,250,000 |
| `mobile-fast3g` | 1.6 Mbps | 750 kbps | 150 ms | 200,000 |

`mobile-fast3g`'s values match Lighthouse's standard "Fast 3G" throttling
profile. Every cold-load measurement uses a fresh Playwright browser context
(`browser.newContext()`), which starts with empty HTTP cache and empty
IndexedDB/Cache Storage, i.e. every rep is a genuine first-time-visitor cold
load, not a warm reload.

Mobile emulation: viewport 390x844, `deviceScaleFactor` 3, `isMobile: true`,
`hasTouch: true`, a Chrome-on-Android user agent string reporting the actual
Chromium build under test (this is Chromium the whole way through, not real
WebKit/Safari -- see Limitations).

### Models served locally

All local-mode measurements serve model files from a plain Node
`http.createServer` static file server on `127.0.0.1`, so the only network
variable under CDP throttling is bytes transferred, not real-world CDN/DNS/TLS
variance (that is measured separately, see "Real-world HF Hub direct load"
below). The transformers.js runtime (`transformers.min.js`) and its ONNX
Runtime Web WASM binary are copied from `node_modules` into `web/vendor/` for
the same reason: to keep jsDelivr's CDN out of the measurement. See
"WASM runtime is not free" for why this runtime copy turned out to matter for
the result, not just for measurement hygiene.

### What "cold load" measures

`cold_load_ms` is `performance.now()` immediately before calling
transformers.js's `pipeline(task, modelId, { dtype, device: "wasm" })` to
immediately after it resolves. That call, in sequence, fetches the tokenizer
files, fetches the config, fetches the ONNX model weights, initializes the
ONNX Runtime WASM backend (fetching its `.wasm`/`.mjs` files the first time
any session is created in that page), and builds the inference session. It is
the number a real first-time visitor would experience as "how long until the
page can classify anything," which is what issue #1 and PLAN.md section 2.1
ask for.

`first_inference_ms` is the first `pipe(text)` call after cold load (pays any
one-time JIT/session-warmup cost). `per_sentence_latency_ms` pools the
remaining 99 (or, for the warmup sentence's run, all 100) sentence latencies
across every successful repeat of a given (model, network condition) cell and
reports p50/p95 over the pooled set.

### Repeat counts (deviation from the original 3-cold-runs-everywhere plan)

The brief called for 3 cold runs per (model, network condition) cell,
uniformly. Once the first `mobile-4g` numbers came back (see "WASM runtime is
not free"), it became clear that repeating the two largest models 3 times on
`mobile-fast3g` would cost 8-14 minutes *per repeat* for a result that is
already obviously and overwhelmingly over any reasonable budget -- rerunning
it three times adds confidence about a conclusion that is not in doubt, at a
cost disproportionate to a one-evening timebox. The repeat counts actually
used:

| Model tier | `desktop-unthrottled` | `mobile-4g` | `mobile-fast3g` |
|---|---|---|---|
| tiny (ckip-bert-tiny-ner) | 3 | 3 | 3 (see timeout note below) |
| large (xenova-bert-base-chinese, xenova-mbert-ner-hrl) | 3 | 3 | **1**, capped at 90 s |

`xenova-paraphrase-minilm-l3` (added after `ckip-albert-tiny-ner` turned out
to be unsupported, see below) got the tiny-tier treatment: 3 reps on all
three conditions, run from a separate script (`scripts/run_benchmark_extra.mjs`)
after the main matrix had already finished.

fp32 is not measured with the same rigor as int8: PLAN.md section 3.3 already
commits to shipping int8 (path B distillation and M2's export both target
quantized weights), so fp32 is a secondary reference point, not a deployment
candidate. It got 1 cold-load rep on `mobile-4g` for the two small models;
for the two large models fp32 was not measured empirically at all (390 MB and
676 MB fp32 on a throttled mobile connection is not an interesting
measurement -- it obviously fails -- so that time went toward more int8 repeats
instead). Its cold-load time is instead calculated from the model's own
measured int8 ms-per-byte throughput on that condition, scaled to the fp32
byte count; this is flagged explicitly wherever it appears.

### A timeout that needed correcting mid-run (twice)

The first `mobile-fast3g` timeout for the tiny tier was set to 180 s, based on
model-bytes-only arithmetic (11.11 MiB / 200 KB/s ~= 57 s). That ignored the
WASM runtime download (see next section), so the actual requirement is closer
to (22.48 + 11.11) MiB / 200 KB/s ~= 177 s -- right at the edge of the original
180 s cap, plus per-request RTT overhead on 5 small tokenizer/config files.
The first two `ckip-bert-tiny-ner` `mobile-fast3g` reps hit this timeout
before completing. `scripts/run_benchmark.mjs` was corrected to 300 s for the
tiny tier for future runs (see the comment at the `fast3gTimeout` assignment);
the affected cell was re-measured with `scripts/run_bert_tiny_fast3g_fixup.mjs`
after the main run finished, to get real completion numbers rather than
reporting an uninformative timeout for the smallest usable model.

The same mistake happened again, independently, in
`scripts/run_benchmark_extra.mjs`: that script was written (to add
`xenova-paraphrase-minilm-l3` after `ckip-albert-tiny-ner` turned out to be
unsupported) before this exact lesson had been internalized as "every
network-condition loop needs a size-aware timeout," not "180 s worked for the
main matrix's structure, reuse it." All 3 of that model's `mobile-fast3g` reps
came back as timeouts under the same 180 s cap ((22.48 + 16.64) MiB /
200 KB/s ~= 196 s, again over budget). Re-measured the same way, with
`scripts/run_minilm_fast3g_fixup.mjs` at a 300 s timeout. Recorded here rather
than quietly fixed and forgotten, because a mistake repeating despite already
being written down once is itself worth knowing for M2: a fixed per-condition
timeout table, computed from `(wasm_size + model_size) / throughput` rather
than copy-pasted, would have avoided both instances.

All timeout attempts and both corrected re-measurements are preserved in
`results/s1_results.json` (`raw` keeps every attempt including the timeouts;
`summary` is computed only from the runs that actually completed).

## Model candidates: what actually exists

The task brief listed candidate model IDs to validate rather than assume. All
validation below used the live `https://huggingface.co/api/models/<id>`
endpoint and HEAD requests against `resolve/main/<file>`, not prior knowledge:

| Candidate (as given) | Exists? | Notes |
|---|---|---|
| `Xenova/bert-base-chinese` | Yes | `pipeline_tag: fill-mask`, no NER head -- used with the `feature-extraction` pipeline, not `token-classification` |
| `Xenova/distilbert-base-multilingual-cased` | **No** (HTTP 401/does not exist under this name) | The base checkpoint exists as `distilbert/distilbert-base-multilingual-cased`, but nobody has published a transformers.js ONNX conversion of it under `Xenova/` or `onnx-community/`. Dropped; not substituted, since the other three real candidates already covered the needed size range. |
| `Xenova/bert-base-multilingual-cased-ner-hrl` | Yes | `pipeline_tag: token-classification`, a real NER head |
| `Xenova/paraphrase-multilingual-MiniLM-L12-v2` | Yes | feature-extraction; int8 turned out to be 112.81 MiB, not "small" as the brief assumed (see below) |
| `Xenova/multilingual-e5-small` | Yes | feature-extraction; int8 112.81 MiB, same size class as MiniLM-L12 above (both are 12-layer, 384-dim encoders) |
| `ckiplab/bert-tiny-chinese-ner` | Yes, no ONNX | 4-layer BERT, hidden 312, 21128 vocab, exported successfully (below) |
| `ckiplab/albert-tiny-chinese-ner` | Yes, no ONNX | ALBERT, hidden 312 / embedding 128, 4 layers with shared parameters; exported successfully but **not loadable by transformers.js 4.2.0** (below) |
| `ckiplab/bert-base-chinese-ner` | Yes, no ONNX | Not used: at ~388 MiB fp32 (pytorch_model.bin 407,021,303 bytes) it is the same size class as `Xenova/bert-base-chinese`, which was already covering that point with a pre-converted, no-export-risk model |

The brief's assumption that `Xenova/paraphrase-multilingual-MiniLM-L12-v2` and
`Xenova/multilingual-e5-small` would serve as "small size points" did not
hold: both are 470 MB fp32 / 112.8 MiB int8, essentially the same size class
as `Xenova/bert-base-chinese` (390 MB fp32 / 98.8 MiB int8). Neither was used
in the final matrix; `Xenova/paraphrase-MiniLM-L3-v2` (see below) filled the
small-size gap instead.

## ONNX export: the M2 preview

This is the step the brief called "what M2 most wants to know." Both CKIP
tiny models exported successfully on the first attempt with `optimum-cli`;
one of the two then failed at the transformers.js loading step, not export.

### `ckiplab/bert-tiny-chinese-ner` -- success

```
uv run --python 3.11 --with-requirements requirements.txt optimum-cli export onnx \
  --model ckiplab/bert-tiny-chinese-ner --task token-classification \
  models/ckip-bert-tiny-ner-raw
```

Exit code 0. Output: `model.onnx`, 45,934,567 bytes (43.81 MiB). Two
warnings, neither fatal: a `torch_dtype` deprecation notice, and "Weight
deduplication check in the ONNX export requires accelerate" (not installed;
deduplication check skipped, export still correct). Dynamic int8
quantization (`onnxruntime.quantization.quantize_dynamic`, `QInt8`) produced
`model_quantized.onnx` at 11,654,582 bytes (11.11 MiB), a 74.6% size
reduction. This model loaded and ran correctly through transformers.js's
`token-classification` pipeline in every subsequent test.

### `ckiplab/albert-tiny-chinese-ner` -- export succeeded, transformers.js load failed

```
uv run --python 3.11 --with-requirements requirements.txt optimum-cli export onnx \
  --model ckiplab/albert-tiny-chinese-ner --task token-classification \
  models/ckip-albert-tiny-ner-raw
```

Exit code 0. One additional warning beyond the two above: `[x] values not
close enough, max diff: 7.82012939453125e-05 (atol: 1e-05)` on the exported
model's logits vs. the PyTorch reference -- within normal fp32 export
tolerance, not a correctness concern. Output: `model.onnx`, 16,125,208 bytes
(15.38 MiB); quantized to `model_quantized.onnx`, 8,846,848 bytes (8.44 MiB,
a smaller 45% reduction than BERT-tiny's, consistent with ALBERT's
cross-layer parameter sharing putting proportionally more of the remaining
weight in the embedding matrix and classifier head, which quantize less
aggressively than the shared transformer block).

The ONNX file loads fine with `onnxruntime` directly. It does not load in
`@huggingface/transformers` 4.2.0. The exact failure, from
`window.runBenchmark`'s probe run (also in
`results/s1_results.json` under `models["ckip-albert-tiny-ner"].unsupported_error`):

```
Error: Unsupported model type: albert
```

transformers.js 4.2.0 does not register an ALBERT model class. This is a
JS-runtime limitation, not an export or ONNX-op-support problem -- the
exported file itself is valid. **Implication for M2**: if path B (distillation
to a small student) is taken and ALBERT's parameter sharing is attractive for
its size, the export half of the pipeline works today, but the browser half
does not, on the transformers.js version current at this spike's date. That
would need either a newer transformers.js release (worth rechecking at M2
time, since this is exactly the kind of gap that gets closed over a
release or two) or a plain BERT-architecture student instead. Per the task
brief's own fallback, the matrix below proceeds with BERT-tiny only for the
"exported by us" size point, and adds a fifth pre-converted model
(`Xenova/paraphrase-MiniLM-L3-v2`) to keep at least four working size points
after ALBERT dropped out (see next section).

## Version pinning: what actually resolved (not what the brief assumed)

The task brief suggested transformers.js "3.x" and left Python versions
unspecified. Both needed correction against the real package registries
before anything would install:

- **`@huggingface/transformers`**: latest stable on npm at spike time is
  **4.2.0**, not a 3.x release (there is a `4.0.0-next.11` prerelease tag but
  4.2.0 is `latest`). Pinned to 4.2.0.
- **`optimum-cli export onnx` no longer ships in the `optimum` package.**
  HuggingFace split ONNX export into a separate `optimum-onnx` package
  (currently 0.1.0); `optimum` itself now only provides the CLI shell and
  hardware-vendor extras (`optimum-intel`, `optimum-habana`, etc.).
  `optimum-onnx[onnxruntime]==0.1.0` is what actually registers
  `optimum-cli export onnx`.
- **`optimum-onnx==0.1.0` pins `optimum~=2.1.0` and `transformers<4.58.0,>=4.36`.**
  This ruled out both PyPI's `optimum` latest (2.3.0) and `transformers`
  latest (5.16.1) for the export environment. Resolved to `optimum==2.1.0`
  and `transformers==4.57.6` (the newest release under the `<4.58.0` cap).
- **`transformers==4.57.6` requires `huggingface_hub>=0.34.0,<1.0`.** PyPI's
  `huggingface_hub` latest is 1.30.0 (post-1.0). Resolved to `0.36.2` (newest
  under the `<1.0` cap); this is also used for the plain model-file downloads
  in `scripts/download_models.py`, so the whole Python side of this spike
  uses one `huggingface_hub` version.
- **`numpy` dropped Python 3.11 support at 2.5.0** (this project pins Python
  3.11 in `.python-version`). Resolved to `numpy==2.4.6`, the newest release
  with a `cp311` wheel.

All of the above was discovered by letting `uv run --with-requirements`
report the actual conflict on each attempt (see git history of this file's
directory for the iteration), not by reading changelogs in advance. Final
resolved versions, confirmed via `importlib.metadata.version()` after
install: `optimum 2.1.0`, `optimum-onnx 0.1.0`, `transformers 4.57.6`,
`onnx 1.22.0`, `onnxruntime 1.29.0`, `huggingface_hub 0.36.2`, `torch 2.14.0`,
`numpy 2.4.6`. Exact pins are in `requirements.txt`.

## WASM runtime is not free

The single most decision-relevant finding, easy to miss if you only look at
model file sizes: **the ONNX Runtime Web WASM binary that transformers.js
loads by default is 23,567,050 bytes (22.48 MiB), and it is fetched fresh on
every true cold visit**, in addition to whatever the model itself weighs.

`web/index.html` does not set any Cross-Origin-Opener-Policy /
Cross-Origin-Embedder-Policy headers (a plain static file server, and by
extension a default GitHub Pages deployment, does not send them either), so
`SharedArrayBuffer` is unavailable (confirmed: every run recorded
`shared_array_buffer_available: false`). Per transformers.js's own default
selection logic (`dist/transformers.web.js`, the `ensureWasmLoaded`/`ONNX_ENV.wasm.wasmPaths`
block), non-Safari browsers -- Chromium included, what this spike tested --
get routed to `ort-wasm-simd-threaded.asyncify.wasm`, the largest of the four
WASM builds `onnxruntime-web` ships:

| Build | Size |
|---|---|
| `ort-wasm-simd-threaded.wasm` | 12.34 MiB |
| `ort-wasm-simd-threaded.jspi.wasm` | 13.88 MiB |
| `ort-wasm-simd-threaded.asyncify.wasm` | **22.48 MiB (what Chromium gets by default)** |
| `ort-wasm-simd-threaded.jsep.wasm` | 24.89 MiB |

This means a literal reading of "3 seconds on a throttled mobile connection"
cannot be met by *any* model size on the default transformers.js/WASM path,
because the runtime alone costs 22.48 MiB / 1.25 MB/s ~= 18 s on `mobile-4g`
before a single byte of model weight is even requested (cold-load is
sequential: the runtime and the model are not fetched concurrently, evidenced
by observed cold-load times matching the *sum* of runtime-time and
model-time, not the max of the two -- see the `mobile-4g` numbers below,
which is why this shows up as an additive floor rather than something a
larger download pipe could hide). The recommended-thresholds section below
addresses this rather than working around it.

## Results

Full raw data (every rep, including timed-out attempts, plus the metadata
block with exact tool/library versions and CDP network parameters) is in
[`results/s1_results.json`](results/s1_results.json).

### Size and cold-load time (int8/q8, the deployment target)

| Model | Task | int8 size | desktop cold (median, n=3) | mobile-4g cold (median, n=3) | mobile-fast3g cold (median, n=3) |
|---|---|---|---|---|---|
| `ckip-albert-tiny-ner` | token-classification | 8.44 MiB | **UNSUPPORTED** -- `Error: Unsupported model type: albert` | -- | -- |
| `ckip-bert-tiny-ner` | token-classification | 11.11 MiB | 322.6 ms | 29,170.0 ms (29.2 s) | 179,609.2 ms (179.6 s) |
| `xenova-paraphrase-minilm-l3` | feature-extraction | 16.64 MiB | 342.0 ms | 34,016.9 ms (34.0 s) | 209,931.3 ms (209.9 s) |
| `xenova-bert-base-chinese` | feature-extraction | 98.80 MiB | 628.6 ms | 102,960.8 ms (103.0 s) | timed out at 90 s (n=1, capped, see Methodology) |
| `xenova-mbert-ner-hrl` | token-classification | 170.23 MiB | 723.8 ms | 164,986.3 ms (165.0 s) | timed out at 90 s (n=1, capped, see Methodology) |

Every `mobile-4g` and corrected `mobile-fast3g` cell has a spread under 30 ms
across its 3 reps (often under 10 ms) -- CDP network emulation on localhost is
extremely reproducible, in sharp contrast to the real-network numbers below.

### fp32 cold load, mobile-4g (secondary reference, not a deployment target)

| Model | fp32 size | mobile-4g cold load |
|---|---|---|
| `ckip-bert-tiny-ner` | 43.81 MiB | 56,641.3 ms (56.6 s) -- measured, n=1 |
| `xenova-paraphrase-minilm-l3` | 65.84 MiB | 75,349.3 ms (75.3 s) -- measured, n=1 |
| `xenova-bert-base-chinese` | 390.46 MiB | 406,919.8 ms (6.8 min) -- **calculated**, not measured |
| `xenova-mbert-ner-hrl` | 676.48 MiB | 655,659.7 ms (10.9 min) -- **calculated**, not measured |

### Per-sentence inference latency (pooled p50/p95 across all completed reps of a condition, dtype q8)

| Model | desktop | mobile-4g | mobile-fast3g |
|---|---|---|---|
| `ckip-bert-tiny-ner` | 4.0 / 8.1 ms | 4.0 / 8.3 ms | 4.0 / 8.3 ms |
| `xenova-paraphrase-minilm-l3` | 4.3 / 8.8 ms | 4.3 / 8.7 ms | 4.3 / 8.7 ms |
| `xenova-bert-base-chinese` | 94.9 / 175.0 ms | 92.4 / 173.9 ms | n/a (no completed fast3g rep) |
| `xenova-mbert-ner-hrl` | 58.9 / 129.2 ms | 58.4 / 129.1 ms | n/a (no completed fast3g rep) |

p50/p95 are within 2 ms of each other across network conditions for every
model, confirming inference latency is local-compute-bound, not
network-bound, once the model has loaded.

### Real-world HF Hub direct load (real internet, no CDP throttle, this environment's measured ~11.6 MB/s)

| Model | int8 size | cold load |
|---|---|---|
| `xenova-paraphrase-minilm-l3` | 16.64 MiB | 3,959.7 ms |
| `xenova-bert-base-chinese` | 98.80 MiB | 8,876.8 ms |
| `xenova-mbert-ner-hrl` | 170.23 MiB | 13,489.4 ms |

All three are single-digit-to-low-double-digit seconds -- far faster than the
equivalent `mobile-4g` cell, because this measures a fast, low-latency real
connection with no artificial throttle, not a phone on a cellular network.
It is here as a sanity check on CDN behavior (see Methodology), not as a
mobile-budget number.

## Recommended thresholds for PLAN section 2.1

PLAN.md section 2.1's defaults (<=50 MB "can fit in the browser", >100 MB
"cannot") are being asked to do two jobs at once: gate on *cold-load time*
and, implicitly, gate on *inference latency*. This spike's numbers say those
two need separate thresholds, and that the cold-load threshold has to be
stated as a function of network condition, because on a throttled mobile
connection the fixed ~22.5 MiB WASM runtime cost already dominates over
plausible model sizes (see "WASM runtime is not free" above).

**1. Redefine the "3 second" budget as a WiFi/desktop-class-bandwidth budget,
not a throttled-4G budget.** Under `desktop-unthrottled` conditions (which
also approximates a realistic WiFi visitor, and is close to what the
`hf-hub-direct` real-network numbers show for this environment's actual
bandwidth), every model tested loads in well under 1 second locally, and the
two Xenova models loaded from the real HF Hub CDN in single-digit seconds.
The literal PLAN.md "3 seconds" bar is achievable, comfortably, for every
model size tested here, *as long as the visitor is not on a throttled mobile
connection*. Recommendation: keep 3 seconds as the WiFi/desktop target used
for `docs/decisions/M1.md`'s go/no-go language, and add an explicit second
number for the throttled-mobile case (next point) rather than requiring one
number to cover both.

**2. For `mobile-4g` specifically, the WASM runtime's ~18 s (22.48 MiB /
1.25 MB/s) is a fixed floor that no model-size choice removes.** Given that
floor, a size threshold should be expressed as "additional seconds beyond
~18 s," not as an absolute pass/fail on 3 s:

| int8 model size | Measured/calculated mobile-4g cold load | Seconds beyond the WASM floor |
|---|---|---|
| ckip-bert-tiny-ner, 11.11 MiB | 29.17 s (measured, n=3, <10ms spread) | ~11 s |
| xenova-paraphrase-minilm-l3, 16.64 MiB | 34.02 s (measured, n=3, <15ms spread) | ~16 s |
| xenova-bert-base-chinese, 98.80 MiB | 102.96 s (measured, n=3, <5ms spread) | ~85 s |
| xenova-mbert-ner-hrl, 170.23 MiB | 165.0 s (measured, n=3) | ~147 s |

If M2 accepts a first-visit budget on the order of **30 seconds on 4G**
(returning visitors are fast regardless, because transformers.js's default
browser-cache behavior means the WASM runtime and model are only fetched
once per browser profile -- this spike's fresh-context methodology
deliberately measures the worst case, not the typical case), the measured
data brackets the threshold tightly: 11.11 MiB clears it (29.17 s), 16.64 MiB
misses it (34.02 s). The threshold that falls out of today's numbers is
**an int8 model under roughly 15 MiB**, interpolated between those two
measured points. That is a real downward revision from PLAN.md's default
50 MiB, and it comes entirely from the WASM floor, not from the model
itself -- a 50 MiB int8 model was never going to be the bottleneck; the
runtime was.

**3. `mobile-fast3g` is not a realistic *first-load* target for this stack
at any size tested.** Even the smallest working model plus the WASM runtime
needs on the order of 3 minutes at 1.6 Mbps (see the corrected
re-measurement below). Recommendation: PLAN.md should not gate the M1 path
decision on a fast-3G load-time number at all; treat fast-3G as a "does it
eventually work, and does the demo show a loading state" check, not a budget.

**4. The p95 <= 100 ms single-sentence latency bar is a separate, size-driven
question, answered independently of network condition** (inference is local
CPU/WASM compute once the model is loaded: desktop and mobile-4g p50/p95 are
within 2 ms of each other for every model, as expected). It lines up with
the same threshold as point 2, for an independent reason:

| Model | p50 / p95 (ms, pooled desktop+mobile-4g) | Clears 100 ms p95? |
|---|---|---|
| ckip-bert-tiny-ner (11.11 MiB) | 4.0 / 8.3 | **Yes**, by a wide margin |
| xenova-paraphrase-minilm-l3 (16.64 MiB) | 4.3 / 8.7-8.8 | **Yes**, by a wide margin |
| xenova-mbert-ner-hrl (170.23 MiB) | 58.4-58.9 / 129.1-129.2 | No |
| xenova-bert-base-chinese (98.80 MiB) | 92.4-94.9 / 173.9-175.0 | No |

Both a cold-load-time argument (point 2) and an independent inference-latency
argument now point at the same conclusion: the small (~10-17 MiB int8)
size class is the one that actually meets PLAN.md's numbers, at both points
tested; the two ~100-170 MiB models miss both bars, not just one. Nothing was
measured in the 17-99 MiB gap in between, so where exactly the latency curve
crosses 100 ms p95 is not pinned down closer than "somewhere in that range."

**Bottom line for the M1 decision table (section 2.1):** keep the "<=50 MB"
language, but attach it to a *WiFi/desktop* load-time claim, not a mobile-4G
one; add a separate "<=15 MB int8 for a sub-30s mobile-4G first load" line if
M2 wants a real mobile budget; and drop `mobile-fast3g` as a gating
condition for M1, since it fails for every viable model size regardless of
distillation effort.

## Implications for M2

- **Export path for CKIP-family tiny models is real and works today**, for
  plain BERT architectures: `optimum-cli export onnx` plus
  `onnxruntime.quantization.quantize_dynamic` is a two-command pipeline from
  a Hub model with no ONNX conversion to a transformers.js-ready int8 file.
  If path B (distillation, PLAN.md section 2.1) lands on a BERT-architecture
  student, this exact pipeline is ready to reuse, including the directory
  rearrangement documented in this spike's README.
- **Do not plan on ALBERT for the browser path** unless a transformers.js
  upgrade is checked first. The export half works; the runtime half does
  not, as of transformers.js 4.2.0. Re-check `pipeline()`'s supported
  architectures at M2 time -- this is exactly the kind of gap that closes
  over a release or two -- before ruling ALBERT out permanently.
- **Investigate the WASM build size before M2 ships a demo.** transformers.js
  defaults non-Safari browsers to the 22.48 MiB "asyncify" ONNX Runtime Web
  build because no COOP/COEP headers are set. A smaller
  `ort-wasm-simd-threaded.wasm` (12.34 MiB, 45% smaller) exists in the same
  package; whether it works correctly without `SharedArrayBuffer` (i.e.
  without cross-origin-isolation headers, which is the realistic default
  for GitHub Pages) is an open question this spike did not chase down, and
  is worth 30 minutes at the start of M2 given how much of the cold-load
  budget the runtime consumes.
- **Cold-load time is additive (WASM-fetch-then-model-fetch), not
  concurrent**, based on this spike's numbers matching byte-count/throughput
  arithmetic almost exactly. If M2's demo can be restructured to fetch the
  WASM runtime and the model weights concurrently (e.g. by warming the ORT
  WASM backend before or during the model fetch rather than after it, if
  transformers.js exposes a hook for that), the mobile-4G floor could drop
  from ~18 s toward something closer to `max(wasm_time, model_time)` ~= same
  ~18 s only for models smaller than the runtime, which is most of the
  models this spike tested -- worth investigating, not confirmed here.
- **`Xenova/bert-base-multilingual-cased-ner-hrl` is a real, ready-to-use
  NER checkpoint** if M2's walking skeleton (PLAN.md section on M2) wants a
  baseline with an actual NER head rather than a bare encoder run through
  `feature-extraction`. It is also the largest model tested here (170 MiB
  int8), so it is a stress-test of the upper end, not a deployment
  candidate under the thresholds above.
- **Real-world HF Hub CDN load times were fast** in this environment (8.9 s
  for a 98.8 MiB model, no throttle) -- faster than this spike's own
  localhost-plus-CDP-throttle numbers for the equivalent throttled
  condition, as expected, but a useful sanity check that HF Hub itself is
  not a bottleneck relative to GitHub Pages/Release-hosted weights (ADR-0005).

## Limitations

- **Headless, not a real phone.** This measures Chromium's WASM/JS engine
  under CDP-emulated network conditions and an emulated iPhone-sized
  viewport, not a real device. Real phones add thermal throttling, real
  radio-layer variance CDP does not model, and (for Safari specifically) a
  different JS engine and WASM implementation entirely -- issue #1 and
  PLAN.md B3 both call for real-device Safari + Chrome testing at M2; this
  spike is a stand-in that answers "is this even in the right order of
  magnitude" cheaply, not a replacement for that.
- **Chromium only, despite the brief's "Safari + Chrome" framing.** Every
  number here, including the ones with a Chrome-flavored mobile user agent
  string, came from the same Chromium/V8/WASM engine. No WebKit build was
  tested.
- **WASM thread count.** No COOP/COEP headers were set, so
  `SharedArrayBuffer` was unavailable and ONNX Runtime Web ran single-threaded
  regardless of the host machine's core count. This matches a default GitHub
  Pages deployment (M2's planned host, per PLAN.md section 3.3) with no extra
  configuration; if M2 adds cross-origin isolation headers, both the WASM
  build selected (see "WASM runtime is not free") and inference latency could
  change and would need re-measuring.
- **WebGPU: presence only, not exercised.** Every run recorded
  `webgpu_available: true` (`navigator.gpu` exists in this headless Chromium
  build), consistent with the brief's explicit scope cut ("WebGPU 深入" out of
  scope, only note availability). `navigator.gpu` existing does not mean a
  working GPU adapter is available in a headless/sandboxed/CI context; this
  was not tested further.
- **`performance.memory` is Chrome-specific and coarse-grained** (values are
  bucketed for fingerprinting-resistance reasons); the recorded JS heap
  numbers are directional, not precise.
- **The two large models' fp32 cold-load times are calculated, not measured**
  (see Methodology's repeat-count section) -- extrapolated linearly from the
  same model's measured int8 throughput on the same condition, not verified
  against a real fp32 run.
- **`mobile-fast3g` for the two large (large-tier) models is a single capped
  run, not three reps.** The conclusion ("dramatically over budget") is not
  in doubt at these sizes, but the exact millisecond figures for those cells
  carry only n=1 confidence, unlike every other cell's n=3.
- **This is a size/latency spike, not an accuracy benchmark.** The CKIP
  models' entity schema (18 OntoNotes-style types including `PERSON` and
  `ORG` but also `DATE`, `MONEY`, `WORK_OF_ART`, etc.) does not match this
  project's own `PERSON`/`ADDRESS`/`ORG` schema, and `Xenova/bert-base-chinese`
  has no NER head at all (tested via `feature-extraction` instead). None of
  that matters for what this spike measures -- bytes transferred and forward-pass
  wall-clock time -- but these numbers say nothing about which backbone M2
  should actually pick for accuracy; that is ADR-0007's job, informed by M1's
  benchmark, not this spike.
- **Synthetic test sentences.** The 100 sentences used for the per-sentence
  latency loop are `data/testset/v0/test.jsonl`'s first 100 rows (mostly
  `easy`/`medium` tier by construction, since the file is ordered by tier) --
  short, template-generated Traditional Chinese text. Token count, and
  therefore per-sentence latency, would differ for longer real-world inputs.
