.PHONY: setup lint test testset benchmark report

SEED ?= 42

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
	uv run python -m zhtw_pii.eval.benchmark

report:
	uv run python -m zhtw_pii.eval.report
