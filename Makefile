.PHONY: setup lint test testset benchmark report report-check

SEED ?= 42
BASELINES ?= all

# Load ANTHROPIC_API_KEY (and anything else) from a gitignored .env if one
# exists, so `make benchmark` can run the Claude Haiku baseline without
# exporting the key into the shell first. No .env: this expands to nothing
# and `uv run` behaves exactly as before.
ENV_FILE := $(wildcard .env)
UV_ENV := $(if $(ENV_FILE),--env-file $(ENV_FILE),)

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
	uv run $(UV_ENV) --group benchmark python -m zhtw_pii.eval.benchmark --baselines $(BASELINES)

report:
	uv run python -m zhtw_pii.eval.report

report-check:
	uv run python -m zhtw_pii.eval.report --check
