# 0006: Public docs in English, internal planning in Chinese

## Context

Bo-Yu's day-to-day planning happens in Chinese, but this project's
intended readers (hiring managers and engineers at companies outside
Taiwan) mostly read English. Mixing languages inside public-facing files
would make the repository harder to evaluate quickly for that audience.

## Decision

Everything under version control that a visitor to the public repository
would read (README, ADRs, MODEL_CARD, DATA_CARD, SECURITY.md, code
comments) is written in English. Internal planning documents (`internal/`)
stay in Chinese and are excluded from git via `.gitignore`.

## Consequences

Planning can stay fast and informal in the language Bo-Yu thinks in,
without translation overhead on every edit, while nothing a hiring manager
opens is gated behind a language they may not read. The cost is a manual
translation step whenever a decision made in `internal/PLAN.md` needs to
become a public ADR or README update, as happened for this very file.
