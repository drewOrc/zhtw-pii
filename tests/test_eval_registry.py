"""Unit tests for zhtw_pii.eval.registry and the benchmark.py runner.

The runner tests use fake baselines (never the real regex/presidio/gliner2/
llm adapters) so they exercise run_baseline/run_all's control flow -- file
writing, status, exit code -- without any dependency on what happens to be
installed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from zhtw_pii.eval import benchmark, registry
from zhtw_pii.eval.types import BaselineMetadata, BaselineUnavailable, Span

pytestmark = pytest.mark.unit


def test_resolve_selectors_all_expands_to_every_registry_key():
    assert registry.resolve_selectors(["all"]) == list(registry.ALL_KEYS)


def test_resolve_selectors_single_baseline_maps_to_itself():
    assert registry.resolve_selectors(["regex"]) == ["regex"]


def test_resolve_selectors_gliner2_expands_to_both_label_set_variants():
    assert registry.resolve_selectors(["gliner2"]) == ["gliner2_en", "gliner2_zh"]


def test_resolve_selectors_deduplicates_across_overlapping_selectors():
    result = registry.resolve_selectors(["regex", "gliner2", "regex"])
    assert result == ["regex", "gliner2_en", "gliner2_zh"]


def test_resolve_selectors_unknown_selector_raises_key_error():
    with pytest.raises(KeyError):
        registry.resolve_selectors(["not_a_real_baseline"])


def test_build_adapter_regex_returns_a_regex_baseline_instance():
    from zhtw_pii.eval.baselines.regex_rules import RegexBaseline

    adapter = registry.build_adapter("regex")
    assert isinstance(adapter, RegexBaseline)


def test_build_adapter_unknown_key_raises_key_error():
    with pytest.raises(KeyError):
        registry.build_adapter("not_a_real_baseline")


def test_build_adapter_gliner2_variants_construct_with_the_right_name():
    en_adapter = registry.build_adapter("gliner2_en")
    zh_adapter = registry.build_adapter("gliner2_zh")
    assert en_adapter.name == "gliner2_en"
    assert zh_adapter.name == "gliner2_zh"


def test_importing_registry_never_imports_heavy_runtime_dependencies():
    """Constructing/listing baselines must never pull in torch, spacy, etc.

    Run in a fresh subprocess so the check is independent of what earlier
    tests in this session happen to have imported.
    """
    script = (
        "import sys\n"
        "import zhtw_pii.eval.registry\n"
        "heavy = {'torch', 'spacy', 'gliner2', 'anthropic', 'presidio_analyzer'}\n"
        "loaded = heavy & set(sys.modules)\n"
        "assert not loaded, f'heavy modules imported as a side effect: {loaded}'\n"
        "print('ok')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


class _FakeOkAdapter:
    name = "fake_ok"
    label_mapping = {"PERSON": "PERSON"}
    params: dict[str, object] = {"note": "fake"}

    def load(self) -> BaselineMetadata:
        return BaselineMetadata(
            model_id="fake-model",
            model_version="1.0",
            size_mb=1.5,
            data_leaves_machine=False,
            bytes_sent=None,
            package_versions={},
        )

    def predict(self, text: str) -> list[Span]:
        return [Span(start=0, end=3, label="PERSON")] if text else []


class _FakeUnavailableAdapter:
    name = "fake_bad"
    label_mapping: dict[str, str] = {}
    params: dict[str, object] = {}

    def load(self) -> BaselineMetadata:
        raise BaselineUnavailable("fake package not installed")

    def predict(self, text: str) -> list[Span]:
        raise AssertionError("predict should never be called when load() failed")


class _FakeCrashesDuringPredictAdapter:
    name = "fake_crash"
    label_mapping: dict[str, str] = {}
    params: dict[str, object] = {}

    def load(self) -> BaselineMetadata:
        return BaselineMetadata(
            model_id="fake-crash-model",
            model_version="1.0",
            size_mb=None,
            data_leaves_machine=False,
            bytes_sent=None,
            package_versions={},
        )

    def predict(self, text: str) -> list[Span]:
        raise RuntimeError("simulated mid-run model crash")


def _gold_examples():
    from zhtw_pii.eval.types import GoldExample

    return [
        GoldExample(id="e1", text="王小明來了", spans=(Span(0, 3, "PERSON"),), tier="easy"),
        GoldExample(id="e2", text="沒有實體", spans=(), tier="negative"),
    ]


def test_run_baseline_writes_evaluated_result_for_a_working_adapter(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "build_adapter", lambda key: _FakeOkAdapter())
    base_metadata = {
        "hardware": "test",
        "python": "3.11.0",
        "date_utc": "2026-01-01T00:00:00Z",
        "testset_path": "fake.jsonl",
        "testset_sha256": "abc",
        "n_examples": 2,
    }
    result = benchmark.run_baseline(
        "fake_ok", _gold_examples(), warmup=0, out_dir=tmp_path, base_metadata=base_metadata
    )
    assert result["status"] == "evaluated"
    assert result["reason"] is None
    assert result["metrics"]["exact"]["PERSON"]["tp"] == 1
    assert Path(result["predictions_path"]).exists()


def test_run_baseline_marks_unevaluated_when_load_raises_baseline_unavailable(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(registry, "build_adapter", lambda key: _FakeUnavailableAdapter())
    result = benchmark.run_baseline(
        "fake_bad",
        _gold_examples(),
        warmup=0,
        out_dir=tmp_path,
        base_metadata={},
    )
    assert result["status"] == "unevaluated"
    assert result["reason"] == "fake package not installed"
    assert result["metrics"] is None
    assert result["predictions_path"] is None


def test_run_baseline_marks_unevaluated_on_unexpected_predict_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "build_adapter", lambda key: _FakeCrashesDuringPredictAdapter())
    result = benchmark.run_baseline(
        "fake_crash", _gold_examples(), warmup=0, out_dir=tmp_path, base_metadata={}
    )
    assert result["status"] == "unevaluated"
    assert "simulated mid-run model crash" in result["reason"]
    assert result["metrics"] is None


def test_run_all_writes_one_file_per_key_and_exits_nonzero_on_any_unevaluated(
    tmp_path, monkeypatch
):
    testset_path = tmp_path / "test.jsonl"
    rows = [
        {
            "id": "e1",
            "text": "王小明來了",
            "entities": [{"start": 0, "end": 3, "label": "PERSON"}],
            "tier": "easy",
        },
        {"id": "e2", "text": "沒有實體", "entities": [], "tier": "negative"},
    ]
    testset_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )

    monkeypatch.setattr(registry, "resolve_selectors", lambda selectors: ["fake_ok", "fake_bad"])

    def fake_build_adapter(key: str):
        return {"fake_ok": _FakeOkAdapter(), "fake_bad": _FakeUnavailableAdapter()}[key]

    monkeypatch.setattr(registry, "build_adapter", fake_build_adapter)

    out_dir = tmp_path / "out"
    args = benchmark.build_arg_parser().parse_args(
        [
            "--testset",
            str(testset_path),
            "--out",
            str(out_dir),
            "--baselines",
            "fake_ok,fake_bad",
            "--warmup",
            "0",
        ]
    )
    exit_code = benchmark.run_all(args)

    assert exit_code == 1
    ok_result = json.loads((out_dir / "fake_ok.json").read_text(encoding="utf-8"))
    bad_result = json.loads((out_dir / "fake_bad.json").read_text(encoding="utf-8"))
    assert ok_result["status"] == "evaluated"
    assert bad_result["status"] == "unevaluated"
    assert bad_result["reason"] == "fake package not installed"


def test_run_all_exits_zero_when_only_a_working_subset_is_selected(tmp_path, monkeypatch):
    testset_path = tmp_path / "test.jsonl"
    row = {
        "id": "e1",
        "text": "王小明",
        "entities": [{"start": 0, "end": 3, "label": "PERSON"}],
        "tier": "easy",
    }
    testset_path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

    monkeypatch.setattr(registry, "resolve_selectors", lambda selectors: ["fake_ok"])
    monkeypatch.setattr(registry, "build_adapter", lambda key: _FakeOkAdapter())

    out_dir = tmp_path / "out"
    args = benchmark.build_arg_parser().parse_args(
        [
            "--testset",
            str(testset_path),
            "--out",
            str(out_dir),
            "--baselines",
            "fake_ok",
            "--warmup",
            "0",
        ]
    )
    exit_code = benchmark.run_all(args)
    assert exit_code == 0


def test_run_all_respects_limit_flag(tmp_path, monkeypatch):
    testset_path = tmp_path / "test.jsonl"
    rows = [
        {
            "id": f"e{i}",
            "text": "王小明",
            "entities": [{"start": 0, "end": 3, "label": "PERSON"}],
            "tier": "easy",
        }
        for i in range(5)
    ]
    testset_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )

    monkeypatch.setattr(registry, "resolve_selectors", lambda selectors: ["fake_ok"])
    monkeypatch.setattr(registry, "build_adapter", lambda key: _FakeOkAdapter())

    out_dir = tmp_path / "out"
    args = benchmark.build_arg_parser().parse_args(
        [
            "--testset",
            str(testset_path),
            "--out",
            str(out_dir),
            "--baselines",
            "fake_ok",
            "--warmup",
            "0",
            "--limit",
            "2",
        ]
    )
    benchmark.run_all(args)
    result = json.loads((out_dir / "fake_ok.json").read_text(encoding="utf-8"))
    assert result["metadata"]["n_examples"] == 2
