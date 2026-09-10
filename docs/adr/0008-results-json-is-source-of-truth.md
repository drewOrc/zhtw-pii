# 0008: Results JSON is the source of truth

## Context

Every benchmark table in this repository (`docs/benchmark.md`, the
README's Benchmark section) reports numbers that could otherwise be typed
by hand once a benchmark run finishes. Hand-typed numbers drift silently:
a re-run changes `results/benchmark/v0/*.json`, nobody remembers to
re-type every table that quotes it, and a reader cannot tell a stale
number from a current one just by looking at markdown.

## Decision

`results/benchmark/v0/*.json` is the only place a metric value is allowed
to originate. `docs/benchmark.md` and the marked benchmark section inside
`README.md` are generated exclusively by `zhtw_pii/eval/report.py`
(`make report`) from those files; no metric in either document is typed
by hand. `make report-check` (`python -m zhtw_pii.eval.report --check`)
re-renders both documents in memory and diffs the result against what is
committed, so a hand-edited number or a stale README table fails that
check instead of passing silently.

## Consequences

A benchmark re-run only ever requires `make report` to bring the docs
back in sync; there is no second place to remember to update. The cost is
that any number quoted in prose commentary, not only the tables
themselves, must trace back to a `results/*.json` field rather than being
typed from memory, which takes more code (small render helpers in
`report.py`) than writing the sentence directly would have.
