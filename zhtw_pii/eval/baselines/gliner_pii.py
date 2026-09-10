"""GLiNER2-PII zero-shot baseline: fastino/gliner2-privacy-filter-PII-multi.

Confirmed to exist via the Hugging Face Hub API (not assumed from
training-data memory): 84,745 downloads at the time this was written,
apache-2.0, `library_name: gliner2`, loadable through the official
`gliner2` package (`pip install "gliner2[local]"`,
`GLiNER2.from_pretrained(...)`). Its own model card names itself
"GLiNER2-PII", matching this project's baseline name in
internal/PLAN.md section 5.

Two label-set variants are registered separately in registry.py:
`gliner2_en` (English label strings) and `gliner2_zh` (Chinese label
strings). Both are always evaluated and reported as separate rows; see
that module's docstring for why neither is chosen based on which one
performs better here.

Two things confirmed empirically before this adapter was finalized (ad
hoc checks against the raw `gliner2` package, not assumed from the model
card or from training-data memory):

- The model's 42 trained labels (see its model card) do not include an
  organization/company label at all; it is otherwise a PII-specific
  model. Despite that, querying it with "organization name" (a label it
  was never fine-tuned on) correctly extracts an organization span from
  an English sentence: GLiNER's zero-shot label generalization holds even
  for a label outside the trained set. ORG is therefore queried the same
  way as PERSON and ADDRESS below, not omitted.
- On Traditional Chinese input, the same "organization name" query (and
  "person name" / "address") returns nothing, down to threshold 0.02, on
  realistic in-context sentences; only a bare, context-free name
  ("王小明" alone) surfaces at a very low threshold. Combined with the
  first point, this isolates the failure to **script/language transfer,
  not label familiarity**: the model generalizes to unseen label
  semantics but not reliably to Chinese-script entity content once it is
  embedded in a longer sentence. Its declared supported languages are
  en/fr/es/de/it/pt/nl; zh is not among them. The full v0 test set (which
  is mostly short, template-driven sentences, not just bare names) shows
  this as a tier-dependent gap rather than a flat zero: see
  `docs/benchmark.md`'s Limitations section for the actual by-tier
  numbers. Running it anyway, under both label languages, is this
  benchmark's actual question about it, not an oversight.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Literal

from zhtw_pii.eval.types import BaselineMetadata, BaselineUnavailable, Span

MODEL_ID = "fastino/gliner2-privacy-filter-PII-multi"
MODEL_REVISION = "c153999da5f4c509df4322b0c6a1baf3d2c284d7"
THRESHOLD = 0.5

_LABEL_SETS: dict[str, dict[str, str]] = {
    "en": {"person name": "PERSON", "address": "ADDRESS", "organization name": "ORG"},
    "zh": {"人名": "PERSON", "地址": "ADDRESS", "公司或機構名稱": "ORG"},
}


def _package_version(dist_name: str) -> str:
    try:
        return version(dist_name)
    except PackageNotFoundError:
        return "unknown"


def _model_size_mb() -> float | None:
    try:
        from huggingface_hub import snapshot_download

        snapshot_path = Path(snapshot_download(MODEL_ID, revision=MODEL_REVISION))
        total_bytes = sum(f.stat().st_size for f in snapshot_path.rglob("*") if f.is_file())
        return round(total_bytes / (1024 * 1024), 2)
    except Exception:  # noqa: BLE001 - size is best-effort, not load-critical
        return None


class GlinerBaseline:
    """Adapter over the official `gliner2` package's `GLiNER2.extract_entities`."""

    def __init__(self, label_set: Literal["en", "zh"]) -> None:
        if label_set not in _LABEL_SETS:
            raise ValueError(f"unknown GLiNER2 label set: {label_set!r}; expected 'en' or 'zh'")
        query_to_pii_label = _LABEL_SETS[label_set]
        self.name = f"gliner2_{label_set}"
        self.label_mapping = dict(query_to_pii_label)
        self._query_labels = tuple(query_to_pii_label)
        self.params: dict[str, object] = {
            "threshold": THRESHOLD,
            "query_labels": list(self._query_labels),
        }
        self._model = None

    def load(self) -> BaselineMetadata:
        try:
            from gliner2 import GLiNER2
        except ImportError as exc:
            raise BaselineUnavailable(
                f"gliner2 package not installed (pip install 'gliner2[local]'): {exc}"
            ) from exc

        try:
            try:
                self._model = GLiNER2.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
            except TypeError:
                # Older gliner2 releases may not accept a `revision` kwarg.
                self._model = GLiNER2.from_pretrained(MODEL_ID)
        except Exception as exc:  # noqa: BLE001 - any load failure means unevaluated
            raise BaselineUnavailable(
                f"failed to load {MODEL_ID}@{MODEL_REVISION}: {type(exc).__name__}: {exc}"
            ) from exc

        package_versions = {"gliner2": _package_version("gliner2")}
        try:
            import torch

            package_versions["torch"] = torch.__version__
        except ImportError:
            pass

        return BaselineMetadata(
            model_id=MODEL_ID,
            model_version=MODEL_REVISION,
            size_mb=_model_size_mb(),
            data_leaves_machine=False,
            bytes_sent=None,
            package_versions=package_versions,
        )

    def predict(self, text: str) -> list[Span]:
        if self._model is None:
            raise RuntimeError("GlinerBaseline.predict called before load()")
        if not text:
            return []
        result = self._model.extract_entities(
            text,
            list(self._query_labels),
            threshold=THRESHOLD,
            include_spans=True,
        )
        spans = [
            span
            for query_label, hits in result.get("entities", {}).items()
            if (mapped := self.label_mapping.get(query_label)) is not None
            for span in _hits_to_spans(hits, text, mapped)
        ]
        spans.sort(key=lambda span: (span.start, span.end, span.label))
        return spans


def _hits_to_spans(hits: list[object], text: str, label: str) -> list[Span]:
    """Convert one label's extracted hits into spans.

    Handles two possible shapes for a hit, since the model card's own
    usage examples are inconsistent about whether `include_spans=True`
    returns structured `{start, end, text}` dicts or plain strings: a
    dict with `start`/`end` is used directly; a plain string falls back
    to `str.find`, tracking the search cursor so repeated values do not
    all resolve to the first occurrence.
    """
    spans: list[Span] = []
    search_from = 0
    for hit in hits:
        if isinstance(hit, dict) and "start" in hit and "end" in hit:
            spans.append(Span(start=int(hit["start"]), end=int(hit["end"]), label=label))
            continue
        value = hit["text"] if isinstance(hit, dict) else str(hit)
        found_at = text.find(value, search_from)
        if found_at == -1:
            found_at = text.find(value)
        if found_at == -1:
            continue
        spans.append(Span(start=found_at, end=found_at + len(value), label=label))
        search_from = found_at + len(value)
    return spans
