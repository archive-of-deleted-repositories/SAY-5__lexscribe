.PHONY: dev fmt lint typecheck test test-unit test-integration migrate seed seed-edgar eval bench bench-eval clean install

PY ?= python3
VENV ?= .venv
BIN := $(VENV)/bin

install:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -U pip wheel setuptools
	$(BIN)/pip install -e ".[dev]"

dev:
	$(BIN)/uvicorn lexscribe_api.main:app --reload --port 8080

fmt:
	$(BIN)/ruff check --fix .
	$(BIN)/black .

lint:
	$(BIN)/ruff check .
	$(BIN)/black --check .

typecheck:
	$(BIN)/mypy packages/shared/lexscribe_shared packages/retrieval/lexscribe_retrieval

test: test-unit

test-unit:
	$(BIN)/pytest -m "not integration and not contract" -q

test-integration:
	RUN_INTEGRATION=1 $(BIN)/pytest -m integration -q

test-contract:
	$(BIN)/pytest -m contract -q

migrate:
	$(BIN)/alembic upgrade head

migrate-down:
	$(BIN)/alembic downgrade base

seed:
	$(BIN)/python scripts/seed.py

seed-edgar:
	$(BIN)/python scripts/seed_edgar.py

eval:
	$(BIN)/lexscribe eval run --suite mna_v1 --provider fake --output runs/local-$(shell date +%s).json

SCALE ?= small
bench:
	mkdir -p bench/results
	$(BIN)/python bench/bench.py --scale $(SCALE)

bench-legacy:
	bash bench.sh

bench-eval:
	mkdir -p eval/runs
	$(BIN)/lexscribe eval run --suite mna_v1 --provider fake --output eval/runs/$(shell date -u +%Y%m%dT%H%M%SZ).json

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
	find . -type d -name .mypy_cache -prune -exec rm -rf {} +
	find . -type d -name .ruff_cache -prune -exec rm -rf {} +
	find . -type d -name '*.egg-info' -prune -exec rm -rf {} +
