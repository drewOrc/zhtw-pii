# 0001: Benchmark before training

## Context

We do not yet know whether existing tools (Presidio, GLiNER2-PII, an LLM
few-shot baseline) already handle Traditional Chinese PII well enough that
training a new model would add nothing. Spending three weeks training
before answering that question risks building a model nobody needed.

## Decision

Week 1 (M1) is a benchmark-only milestone: no training happens until we
have measured Precision, Recall, and F1 for every candidate baseline on a
frozen, audited synthetic test set. The M1 decision table turns those
numbers into one of three paths: train to beat the best baseline, distill
to shrink it, or stop and publish a null result.

## Consequences

The benchmark table is itself a publishable artifact even if every later
milestone slips or the project stops at M1. It also means the first week's
output is a table, not a model; anyone skimming the repo in week one will
see numbers, not weights, and that is intentional.
