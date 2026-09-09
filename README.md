# zhtw-pii

[![CI](https://github.com/drewOrc/zhtw-pii/actions/workflows/ci.yml/badge.svg)](https://github.com/drewOrc/zhtw-pii/actions/workflows/ci.yml)

Traditional Chinese PII and sensitive-entity detection, benchmarked against
existing tools and runnable fully in the browser.

zhtw-pii detects person names and addresses (personal data) and organization
names (a confidential but non-personal entity type) in Traditional Chinese
text, so a pipeline can flag or redact them before sending data to an
external LLM API. The whole toolchain, synthetic data generation, training
or distillation, evaluation, ONNX export, and a static demo, is open source.

**Status: Day 0 scaffold (pre-M1).** The data generator and test harness
work today; no benchmark numbers exist yet. See Roadmap below.

## Benchmark

All numbers below are placeholders until the Week 1 benchmark (M1) runs.
None of these are measured yet; see [Limitations](#limitations).

| System | PERSON F1 | ADDRESS F1 | ORG F1 | Size | Latency (p95) | Data leaves your device? |
|---|---|---|---|---|---|---|
| Regex + checksum baseline | TBD after M1 | TBD after M1 | TBD after M1 | TBD after M1 | TBD after M1 | No |
| Microsoft Presidio | TBD after M1 | TBD after M1 | TBD after M1 | TBD after M1 | TBD after M1 | No |
| GLiNER2-PII (zero-shot) | TBD after M1 | TBD after M1 | TBD after M1 | TBD after M1 | TBD after M1 | No |
| LLM few-shot (Claude Haiku 4.5) | TBD after M1 | TBD after M1 | TBD after M1 | N/A | TBD after M1 | Yes (sent to the API) |
| **zhtw-pii (this project)** | TBD after M3 | TBD after M3 | TBD after M3 | TBD after M3 | TBD after M3 | No (runs in-browser) |

## Limitations

- **Results are valid only for the synthetic distribution designed in this
  project and do not represent real Taiwanese text.** Every name, address,
  and organization in the test set is generated from public statistical
  lexicons and hand-written templates; see `data/DATA_CARD.md` for exactly
  how, and for the known biases that follow from it.
- This is a Day 0 scaffold. The benchmark (M1), browser pipeline (M2), and
  trained model (M3) have not run yet; every number above is a placeholder.
- v1 does not cover format-defined entities (national ID numbers, unified
  business numbers, phone numbers, emails, credit card numbers). Those are
  solved by regex and checksums with no room for a model to add value; see
  `docs/adr/0002-exclude-format-defined-entities.md`.
- Traditional Chinese only. Simplified Chinese is not a target; it is only
  noted as an unevaluated "does it happen to work" aside if observed.
- This is not a compliance tool. It does not guarantee complete detection
  and must not be used as your only control for personal-data handling.
  See `SECURITY.md`.

## Architecture

```
data/    synthetic generator, testset v0/v1 (deterministic, seeded)
  -> train/   fine-tune or distill (HF transformers; weights not in git)
  -> eval/    benchmark: seqeval + statistical tests (results/*.json is
              the single source of truth; tables are rendered from it)
  -> export/  ONNX + int8 quantization (for transformers.js)
  -> demo/    static page, GitHub Pages (loads the ONNX model client-side)
```

Inference in the demo never leaves the visitor's browser: the page loads
the int8 ONNX model once via transformers.js, then runs token
classification locally on whatever the visitor types. See
`docs/adr/0004-static-demo-precomputed-llm.md` for how the demo compares
against a large LLM without a backend.

## Design decisions

Every non-obvious choice, and the alternatives considered, is written down
as an ADR in `docs/adr/`:

- [0001: Benchmark before training](docs/adr/0001-benchmark-before-training.md)
- [0002: Exclude format-defined entities from v1](docs/adr/0002-exclude-format-defined-entities.md)
- [0003: Fully synthetic data, zero real PII](docs/adr/0003-fully-synthetic-data.md)
- [0004: Static demo with a precomputed large-model column](docs/adr/0004-static-demo-precomputed-llm.md)
- [0005: Model weights on HF Hub and GitHub Releases, not in git](docs/adr/0005-weights-hf-hub-not-git.md)
- [0006: Public docs in English, internal planning in Chinese](docs/adr/0006-english-public-docs.md)

## Reproduce

Requires Python 3.11 and [uv](https://docs.astral.sh/uv/).

```
git clone https://github.com/drewOrc/zhtw-pii
cd zhtw-pii
make setup      # uv sync
make test       # pytest, unit tests only, no network
make testset    # regenerate data/testset/v0/test.jsonl (seed 42)
```

`make testset` run twice with the same seed produces byte-identical output
(verified by a unit test and, once CI exists, by a weekly reproduce job).
`make benchmark` and `make report` exist as CLI entry points but raise
`NotImplementedError` until M1 lands.

## Roadmap

- **M1, Benchmark**: freeze a 300-example synthetic test set, measure
  regex, Presidio, GLiNER2-PII, and an LLM baseline, decide whether to
  train, distill, or stop.
- **M2, Browser pipeline**: export a baseline model to int8 ONNX and get
  the full data-to-browser demo working end to end before any custom
  training happens.
- **M3, Train**: fine-tune or distill zhtw-pii's own model, evaluate on 3
  seeds with significance testing, swap it into the M2 demo if it wins.
- **M4, Ship**: model card, data card, v1.0.0 release, and a portfolio
  write-up.

Full milestone detail, including per-milestone acceptance criteria, lives
in the project's internal planning notes (not published; see
`docs/adr/0006-english-public-docs.md` for why).

## License

Code is licensed under the [MIT License](LICENSE). See `NOTICE` for
third-party dependency licenses and `data/DATA_CARD.md` for the dataset's
intended license.
