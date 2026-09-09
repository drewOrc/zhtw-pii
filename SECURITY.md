# Security Policy

## Reporting a vulnerability

If you find a security issue in zhtw-pii (for example, a way to make the
detector systematically miss PII, or a supply-chain issue in a dependency),
please report it privately rather than opening a public issue.

Email boyu.chen@my.utsa.edu with a description of the issue, steps to
reproduce, and, if you have one, a suggested fix. Expect an initial
response within 5 business days.

Please do not open a public GitHub issue for a security-sensitive report
until a fix has shipped.

## Scope

This applies to the code in this repository: data generation, training,
evaluation, export, and the demo. It does not cover third-party baselines
(Presidio, GLiNER2-PII) evaluated for comparison; report issues in those
projects upstream.

## Important limitation

zhtw-pii does not guarantee complete detection of personal or sensitive
information. Benchmark numbers in this repository are measured against a
synthetic test set (see `data/DATA_CARD.md` and the README Limitations
section); real-world text will contain patterns the model has not seen.

**Do not use this tool as your only compliance control** for personal-data
handling, redaction, or regulatory obligations (for example Taiwan's
Personal Data Protection Act or the GDPR). Treat it as one signal among
several, with human review for anything where a missed detection has legal
or safety consequences.
