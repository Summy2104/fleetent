.DEFAULT_GOAL := help

.PHONY: help install test t lint fmt check typecheck serve admin

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install / sync dependencies
	uv sync

test: ## Run full test suite
	uv run pytest

t: ## Run tests (fail-fast, quiet)
	uv run pytest -x -q

lint: ## Check code style with ruff
	uv run ruff check src tests

fmt: ## Auto-format code with ruff
	uv run ruff format src tests

typecheck: ## Type-check with mypy
	uv run mypy src

check: lint typecheck ## Run lint + typecheck

serve: ## Start HTTP server with auto-reload (port 8000)
	uv run uvicorn mini_agent.server:app --reload

admin: ## Show admin CLI help
	uv run mini-agent-admin --help
