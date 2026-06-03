.DEFAULT_GOAL := help

.PHONY: help install test t test-unit test-unit-ci test-integration test-e2e test-evaluation lint fmt check typecheck serve admin

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install / sync dependencies
	uv sync

test: ## Run full test suite
	uv run pytest

t: ## Run tests (fail-fast, quiet)
	uv run pytest -x -q

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

lint: ## Check code style with ruff
	uv run ruff check src tests

fmt: ## Auto-format code with ruff
	uv run ruff format src tests

typecheck: ## Type-check with mypy
	uv run mypy src

check: lint typecheck ## Run lint + typecheck

serve: ## Start HTTP server with auto-reload (port 8765)
	uv run uvicorn fleetent.server:app --reload --port 8765

admin: ## Show admin CLI help
	uv run fleetent-admin --help
