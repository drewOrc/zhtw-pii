"""Microsoft Presidio baseline with a spaCy Traditional Chinese NLP engine.

`presidio-analyzer` and spaCy (plus a Chinese pipeline) are optional,
heavy dependencies (see the `benchmark` dependency group in
pyproject.toml); importing them happens only inside `load()`, never at
module import time, so listing or filtering baselines never requires them
to be installed.

Model selection: presidio's built-in `SpacyRecognizer` finds PERSON/ORG/
GPE/LOCATION through whichever spaCy pipeline is configured for the "zh"
language. This adapter tries, in priority order, the largest installed
Chinese-capable spaCy pipeline (`zh_core_web_lg` > `zh_core_web_md` >
`zh_core_web_sm`) and records which one actually loaded in
`metadata.model_id`. None of the three is a project dependency (see the
`benchmark` group); a clean `uv sync` never triggers a spaCy model
download.
"""

from __future__ import annotations

import importlib.util
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from zhtw_pii.eval.types import BaselineMetadata, BaselineUnavailable, Span

_SPACY_MODEL_PRIORITY: tuple[str, ...] = ("zh_core_web_lg", "zh_core_web_md", "zh_core_web_sm")

_LABEL_MAPPING: dict[str, str] = {
    "PERSON": "PERSON",
    "LOCATION": "ADDRESS",
    "GPE": "ADDRESS",
    "ORGANIZATION": "ORG",
    "ORG": "ORG",
}


def _package_version(dist_name: str) -> str:
    try:
        return version(dist_name)
    except PackageNotFoundError:
        return "unknown"


def _first_installed_spacy_model() -> str:
    for model_name in _SPACY_MODEL_PRIORITY:
        if importlib.util.find_spec(model_name) is not None:
            return model_name
    tried = ", ".join(_SPACY_MODEL_PRIORITY)
    raise BaselineUnavailable(
        f"no Traditional Chinese spaCy model installed (tried, largest first: {tried}); "
        "install one via the `benchmark` dependency group"
    )


def _directory_size_mb(path: Path) -> float | None:
    try:
        total_bytes = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        return round(total_bytes / (1024 * 1024), 2)
    except OSError:
        return None


class PresidioBaseline:
    """Adapter over presidio-analyzer's AnalyzerEngine, configured for zh."""

    name = "presidio"
    label_mapping = dict(_LABEL_MAPPING)
    params: dict[str, object] = {
        "language": "zh",
        "entities": ["PERSON", "LOCATION", "GPE", "ORGANIZATION", "ORG"],
        "model_priority": list(_SPACY_MODEL_PRIORITY),
    }

    def __init__(self) -> None:
        self._analyzer = None

    def load(self) -> BaselineMetadata:
        try:
            import spacy  # pyright: ignore[reportMissingImports]
        except ImportError as exc:
            raise BaselineUnavailable(f"spacy not installed: {exc}") from exc
        try:
            from presidio_analyzer import AnalyzerEngine  # pyright: ignore[reportMissingImports]
            from presidio_analyzer.nlp_engine import (  # pyright: ignore[reportMissingImports]
                NlpEngineProvider,
            )
        except ImportError as exc:
            raise BaselineUnavailable(f"presidio-analyzer not installed: {exc}") from exc

        model_name = _first_installed_spacy_model()

        try:
            nlp_configuration = {
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "zh", "model_name": model_name}],
            }
            nlp_engine = NlpEngineProvider(nlp_configuration=nlp_configuration).create_engine()
            self._analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["zh"])
        except Exception as exc:  # noqa: BLE001 - any setup failure means unevaluated
            raise BaselineUnavailable(
                f"failed to build presidio AnalyzerEngine with {model_name}: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        size_mb = None
        try:
            model_path = Path(spacy.util.get_package_path(model_name))
            size_mb = _directory_size_mb(model_path)
        except Exception:  # noqa: BLE001 - size is best-effort, not load-critical
            pass

        package_versions = {
            "presidio_analyzer": _package_version("presidio-analyzer"),
            "spacy": _package_version("spacy"),
            model_name: _package_version(model_name),
        }
        return BaselineMetadata(
            model_id=f"presidio+spacy:{model_name}",
            model_version=package_versions[model_name],
            size_mb=size_mb,
            data_leaves_machine=False,
            bytes_sent=None,
            package_versions=package_versions,
        )

    def predict(self, text: str) -> list[Span]:
        if self._analyzer is None:
            raise RuntimeError("PresidioBaseline.predict called before load()")
        if not text:
            return []
        results = self._analyzer.analyze(text=text, language="zh")
        spans: list[Span] = []
        for result in results:
            mapped = self.label_mapping.get(result.entity_type)
            if mapped is None:
                continue
            spans.append(Span(start=result.start, end=result.end, label=mapped))
        spans.sort(key=lambda span: (span.start, span.end, span.label))
        return spans
