.PHONY: setup lint test testset benchmark report report-check

SEED ?= 42
BASELINES ?= all

setup:
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run pyright

test:
	uv run pytest -m unit

testset:
	uv run python -m zhtw_pii.data.generate --seed $(SEED) --out data/testset/v0/test.jsonl

benchmark:
	uv run --group benchmark python -m zhtw_pii.eval.benchmark --baselines $(BASELINES)

report:
	uv run python -m zhtw_pii.eval.report

report-check:
	uv run python -m zhtw_pii.eval.report --check
