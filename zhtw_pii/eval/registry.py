"""Maps a `--baselines` CLI selector to one or more registry entries.

A "selector" is what a user types on `--baselines` (e.g. "gliner2"); a
"registry key" is what ends up in a result file's `baseline` field and in
its filename. Most selectors map to exactly one key; "gliner2" maps to
two (`gliner2_en`, `gliner2_zh`) because this project always evaluates
both label sets and reports them as separate rows (internal/PLAN.md
section 5: "not label-picked against the test set").

Importing this module must stay cheap: it imports the baseline *classes*,
not their heavy runtime dependencies. Every adapter below defers
`presidio_analyzer` / `spacy` / `gliner2` / `torch` / `anthropic` imports
to its own `load()` method, so constructing (but not loading) any
baseline, including from this registry, never requires them.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from zhtw_pii.eval.baselines.claude_llm import ClaudeLlmBaseline
from zhtw_pii.eval.baselines.gliner_pii import GlinerBaseline
from zhtw_pii.eval.baselines.presidio_zh import PresidioBaseline
from zhtw_pii.eval.baselines.regex_rules import RegexBaseline
from zhtw_pii.eval.types import BaselineAdapter

ALL_KEYS: tuple[str, ...] = ("regex", "presidio", "gliner2_en", "gliner2_zh", "llm")

_FACTORIES: dict[str, Callable[[], BaselineAdapter]] = {
    "regex": RegexBaseline,
    "presidio": PresidioBaseline,
    "gliner2_en": lambda: GlinerBaseline(label_set="en"),
    "gliner2_zh": lambda: GlinerBaseline(label_set="zh"),
    "llm": ClaudeLlmBaseline,
}

# What a user types on --baselines, expanded to the registry keys it
# produces result files for. "gliner2" intentionally expands to two.
SELECTOR_GROUPS: dict[str, tuple[str, ...]] = {
    "regex": ("regex",),
    "presidio": ("presidio",),
    "gliner2": ("gliner2_en", "gliner2_zh"),
    "llm": ("llm",),
}


def build_adapter(key: str) -> BaselineAdapter:
    """Construct a fresh adapter instance for one registry key.

    Construction itself stays cheap; adapters defer heavy imports to
    `.load()`.
    """
    try:
        factory = _FACTORIES[key]
    except KeyError:
        raise KeyError(f"unknown baseline registry key: {key!r}; known keys: {ALL_KEYS}") from None
    return factory()


def resolve_selectors(selectors: Sequence[str]) -> list[str]:
    """Expand `--baselines` selectors into registry keys, in order, deduplicated.

    A single selector `"all"` expands to every registry key. Any other
    input is a comma-split list of selector names, each looked up in
    `SELECTOR_GROUPS`.
    """
    if len(selectors) == 1 and selectors[0] == "all":
        return list(ALL_KEYS)
    keys: list[str] = []
    for selector in selectors:
        try:
            group = SELECTOR_GROUPS[selector]
        except KeyError:
            known = (*SELECTOR_GROUPS, "all")
            raise KeyError(f"unknown baseline selector: {selector!r}; known: {known}") from None
        for key in group:
            if key not in keys:
                keys.append(key)
    return keys
