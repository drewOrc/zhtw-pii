# 0004: Static demo with a precomputed large-model column

## Context

The demo's most interesting comparison is a small in-browser model against
a large LLM. Running that comparison live would mean either shipping an
API key to the browser (unsafe) or standing up a proxy server (cost and an
abuse surface for a portfolio project).

## Decision

The demo is a static page. The small model runs fully in the visitor's
browser via transformers.js. The large-model column only shows
precomputed results for a fixed set of example sentences, calculated once
offline and baked into the page; free-form visitor input only ever runs
through the in-browser model.

## Consequences

There is no backend, no API key exposure, and no abuse surface, so the
demo can be hosted on GitHub Pages at zero cost indefinitely. The cost is
that a visitor cannot type an arbitrary sentence and see what a large LLM
would say about it, only what the small model says; the page states this
explicitly next to the large-model column.
