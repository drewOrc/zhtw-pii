# 0003: Fully synthetic data, zero real PII

## Context

Training or evaluating a PII detector normally tempts you to use real text
with real names and addresses, because it is more realistic. That also
means handling real personal data, with the legal and reputational risk
that implies for an open-source side project.

## Decision

Every name, address, and organization in the dataset is generated from
public statistical lexicons (surname frequency tables, public place-name
lists) recombined by a template engine, never copied from a real document
or a real person. A blocklist filters out any generated name that happens
to match a known public figure.

## Consequences

Annotation is free and exact, since the generator knows the span of every
entity it inserts; there is no labeling error to audit. The tradeoff is
that synthetic text may not capture every pattern real Traditional Chinese
text contains. The hard tier's noisy variants and a manual audit sample
(recorded in `data/testset/v0/AUDIT.md` once M1 runs it) are how we probe
that gap, and the README Limitations section says so explicitly.
