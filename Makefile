.DEFAULT_GOAL := help

.PHONY: help install test t test-pr test-unit test-unit-ci test-integration test-e2e test-evaluation test-layers lint fmt check typecheck serve admin

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install / sync dependencies
	uv sync

test: ## Run full test suite
	uv run pytest

t: ## Run tests (fail-fast, quiet)
	uv run pytest -x -q

# Quarantine slot for flaky tests (none currently). The permission_gate
# approvals-id pair was de-quarantined after the R1 agent-owned-approval refactor:
# two consecutive full `pytest tests/unit` runs pass clean (2026-06-10).
PR_DESELECT :=

# ruff runs only on files this branch changed vs main: main carries pre-existing
# format/lint debt across other owners' modules, so a whole-tree gate is unviable
# and you are only accountable for files you touched.
test-pr: ## PR gate (must be green): unit (minus quarantine) + layer boundaries + ruff on changed files
	uv run pytest tests/unit -q $(PR_DESELECT)
	uv run python scripts/check_test_layers.py
	@changed="$$( { git diff --name-only --diff-filter=ACMR main...HEAD -- '*.py'; git diff --name-only --diff-filter=ACMR -- '*.py'; git diff --name-only --cached --diff-filter=ACMR -- '*.py'; } | sort -u | while IFS= read -r f; do [ -f "$$f" ] && printf '%s\n' "$$f"; done )"; \
	if [ -n "$$changed" ]; then \
		printf 'ruff on changed files:\n%s\n' "$$changed"; \
		uv run ruff format --check $$changed && uv run ruff check $$changed; \
	else \
		echo "test-pr: no changed .py files vs main; skipping ruff"; \
	fi

test-unit: ## Run unit tests
	uv run pytest tests/unit

test-unit-ci: ## Run CI unit tests with 75% coverage gate
	uv run coverage run --source=src/fleetent -m pytest tests/unit
	uv run coverage report --fail-under=75

test-integration: ## Run integration tests
	uv run pytest tests/integration

test-e2e: ## Run end-to-end tests
	uv run pytest tests/e2e

test-evaluation: ## Run evaluation tests
	uv run pytest tests/evaluation

test-layers: ## Check unit/integration boundaries, including DB-backed unit tests
	uv run python scripts/check_test_layers.py

lint: ## Check code style with ruff
	uv run ruff check src tests scripts

fmt: ## Auto-format code with ruff
	uv run ruff format src tests scripts

typecheck: ## Type-check with mypy
	uv run mypy src

check: lint typecheck ## Run lint + typecheck

serve: ## Start HTTP server with auto-reload (port 8765)
	uv run uvicorn fleetent.server:app --reload --port 8765

admin: ## Show admin CLI help
	uv run fleetent-admin --help
