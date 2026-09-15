.PHONY: setup lint test testset benchmark report report-check audit-sample audit-check

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

# Manual label audit of test set v0 (issue #4). The sample seed is pinned in
# zhtw_pii/data/audit.py and deliberately ignores SEED, so a different sample
# cannot be drawn without a visible code change. audit-sample refuses to
# overwrite an existing AUDIT.md, which may hold answers; only FORCE=1 overrides
# (FORCE=0 or any other value still refuses).
audit-sample:
	uv run python -m zhtw_pii.data.audit sample $(if $(filter 1,$(FORCE)),--force,)

audit-check:
	uv run python -m zhtw_pii.data.audit check
