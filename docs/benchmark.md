# zhtw-pii Benchmark (v0)

Every number below is rendered from `results/benchmark/v0/*.json` by `make report` (`zhtw_pii/eval/report.py`); `make report-check` fails CI if this file or README's benchmark table drifts from those JSON files. See `docs/adr/0008-results-json-is-source-of-truth.md`.

## Method

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


Test set: `data/testset/v0/test.jsonl`, 300 examples, SHA256 `84025f8e7fd50c905258864c3a93349f565e17a75b208f98ad29f431656d69f6`.

Measured on: macOS-26.6.2-arm64-arm-64bit (arm), Python 3.11.14.

## Results

| System | PERSON F1 | ADDRESS F1 | ORG F1 | Micro F1 (exact) | Micro F1 (overlap) | FPR (negatives) | Latency p50/p95 (ms) | Size | Data leaves device? |
|---|---|---|---|---|---|---|---|---|---|
| Regex + lexicon baseline | 0.6617 | 1.0000 | 0.5051 | 0.7106 | 0.9331 | 0.3200 | 0.004 / 0.006 | N/A | no |
| Microsoft Presidio | 0.2718 | 0.0236 | 0.4125 | 0.2228 | 0.6513 | 0.2400 | 3.590 / 5.698 | 663.22 MB | no |
| GLiNER2-PII (English labels) | 0.1800 | 0.0339 | 0.1168 | 0.1333 | 0.3676 | 0.0000 | 39.946 / 46.724 | 1186.80 MB | no |
| GLiNER2-PII (Chinese labels) | 0.1854 | 0.1875 | 0.1168 | 0.1693 | 0.4021 | 0.0000 | 40.524 / 46.754 | 1186.80 MB | no |
| Claude Haiku 4.5 (few-shot) | unevaluated | unevaluated | unevaluated | unevaluated | unevaluated | unevaluated | N/A | N/A |

## Unevaluated baselines

- **Claude Haiku 4.5 (few-shot)**: ANTHROPIC_API_KEY not set

## Results by tier (micro F1, exact / overlap)

| System | easy (exact / overlap) | medium (exact / overlap) | hard (exact / overlap) |
|---|---|---|---|
| Regex + lexicon baseline | 0.9193 / 0.9938 | 0.6805 / 0.9301 | 0.6868 / 0.9585 |
| Microsoft Presidio | 0.4741 / 0.5778 | 0.1851 / 0.6682 | 0.1617 / 0.6979 |
| GLiNER2-PII (English labels) | 0.5913 / 0.6087 | 0.0068 / 0.3265 | 0.0274 / 0.2603 |
| GLiNER2-PII (Chinese labels) | 0.6034 / 0.6207 | 0.0721 / 0.3869 | 0.0274 / 0.2603 |

## Limitations

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
