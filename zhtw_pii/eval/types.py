"""Shared data types for the benchmark runner.

Every baseline adapter and the metrics module speak these types, so a new
baseline only needs to satisfy `BaselineAdapter` and never touches the
scoring or serialization logic directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, order=True)
class Span:
    """A single labeled character span, half-open on `[start, end)`."""

    start: int
    end: int
    label: str

    def to_json_dict(self) -> dict[str, int | str]:
        """Return the plain-dict form used for JSONL prediction files."""
        return {"start": self.start, "end": self.end, "label": self.label}


@dataclass(frozen=True)
class GoldExample:
    """One row of the frozen test set, as needed for scoring."""

    id: str
    text: str
    spans: tuple[Span, ...]
    tier: str


@dataclass(frozen=True)
class BaselineMetadata:
    """Everything about a baseline that does not depend on the test set.

    `size_mb` and `bytes_sent` are `None` when the concept does not apply
    (a regex has no model file; a local model never sends bytes anywhere).
    """

    model_id: str
    model_version: str
    size_mb: float | None
    data_leaves_machine: bool
    bytes_sent: int | None
    package_versions: dict[str, str] = field(default_factory=dict)


class BaselineUnavailable(Exception):
    """Raised when a baseline cannot produce predictions this run.

    The `reason` is written verbatim into the result JSON's `reason` field
    and printed to stderr. Adapters raise this for a missing package, a
    model that fails to load, or a missing credential; the runner must
    never turn this into a silent skip.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class BaselineAdapter(Protocol):
    """What `registry.py` and `benchmark.py` require from every baseline.

    `load()` is where heavy imports and model downloads happen, and where
    `BaselineUnavailable` is expected to be raised; constructing the
    adapter object itself must stay cheap so listing baselines never
    imports torch or spaCy.
    """

    name: str
    label_mapping: dict[str, str]
    params: dict[str, object]

    def load(self) -> BaselineMetadata:
        """Prepare the baseline for prediction, or raise BaselineUnavailable."""
        ...

    def predict(self, text: str) -> list[Span]:
        """Return predicted entity spans for one input string."""
        ...
