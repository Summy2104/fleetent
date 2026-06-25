.DEFAULT_GOAL := help

.PHONY: help install test t test-pr test-unit test-unit-ci test-coverage-ci test-integration test-e2e test-evaluation test-layers lint fmt check typecheck platform-help \
	frontend-install frontend-build test-frontend \
	dev-bootstrap dev-reset platform node-provision node kb-worker agent chat dev-clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

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

test-unit-ci: ## Run CI unit tests with 76% coverage gate
	uv run coverage run --source=src/fleetent -m pytest tests/unit
	uv run coverage report --fail-under=76

test-coverage-ci: ## Run daily unit+integration tests with 88% combined coverage gate
	uv run coverage run --source=src/fleetent -m pytest tests/unit tests/integration
	uv run coverage report --fail-under=88

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

frontend-install: ## Install frontend dependencies
	yarn --cwd frontend install --frozen-lockfile

frontend-build: ## Build frontend static assets
	yarn --cwd frontend build

test-frontend: ## Run frontend tests, coverage, typecheck, and lint
	yarn --cwd frontend vitest run --coverage
	yarn --cwd frontend tsc --noEmit
	yarn --cwd frontend eslint .

platform-help: ## Show platform CLI help
	uv run fleetent platform --help

# ---- local dev stack -------------------------------------------------------
# All data/config lives under a gitignored dev home (override by exporting
# FLEETENT_HOME / DATABASE_URL). These vars are exported ONLY for the dev-stack
# targets below (target-specific), so they never leak into the test targets,
# which isolate FLEETENT_HOME themselves. Run each long-running service in its
# own terminal. NOTE: always `python -m uvicorn` (a bare `uv run uvicorn`
# resolves to a system uvicorn that can't import fleetent).
#
# FLEETENT_SECRET_KEY uses deferred `=` (NOT `:=`): it must be read from
# .dev_secret_key when each recipe RUNS, not at parse time. `dev-reset` deletes
# and regenerates the key mid-invocation (dev-clean → dev-bootstrap), so a
# parse-time `:=` would capture the stale pre-reset key and node-provision would
# encrypt the node service key with a key that no longer matches the file —
# breaking platform ingress with "service key unavailable".
FLEETENT_HOME ?= $(CURDIR)/.fleetent-dev
DATABASE_URL  ?= sqlite:///$(FLEETENT_HOME)/management.db
PLATFORM_PORT ?= 8765
AGENT_PORT    ?= 8766
NODE_ID       ?= local-node
NODE_PLATFORM_URL ?= http://127.0.0.1:$(PLATFORM_PORT)

DEV_TARGETS := dev-bootstrap dev-reset platform node-provision node kb-worker agent chat dev-clean
$(DEV_TARGETS): export FLEETENT_HOME := $(FLEETENT_HOME)
$(DEV_TARGETS): export DATABASE_URL := $(DATABASE_URL)
$(DEV_TARGETS): export NODE_ID := $(NODE_ID)
$(DEV_TARGETS): export NODE_PLATFORM_URL := $(NODE_PLATFORM_URL)
$(DEV_TARGETS): export FLEETENT_SECRET_KEY = $(shell cat "$(FLEETENT_HOME)/.dev_secret_key" 2>/dev/null || true)
$(DEV_TARGETS): export FLEETENT_FORWARDER_HOST_OVERRIDE := 127.0.0.1

dev-bootstrap: ## Init dev home: migrate management DB + seed built-in admin + scaffold env files
	mkdir -p "$(FLEETENT_HOME)"
	uv run python scripts/dev_secret_key.py
	uv run alembic upgrade head
	uv run fleetent platform seed-builtin-admin
	uv run fleetent platform init-config --home "$(FLEETENT_HOME)"
	uv run fleetent node init-config
	uv run fleetent kb-worker init-config

dev-reset: dev-clean dev-bootstrap node-provision ## Wipe + re-init dev home from scratch (clean → bootstrap → provision node)
	@echo "dev home reset: $(FLEETENT_HOME) — start services with 'make platform', 'make node', 'make kb-worker'"

platform: ## Start platform control-plane (admin API/UI), default port 8765
	uv run fleetent platform serve --host 127.0.0.1 --port $(PLATFORM_PORT)

node-provision: ## Register the dev node + write node/.env (idempotent; FORCE=1 to re-key)
	uv run python scripts/dev_node_provision.py $(if $(FORCE),--force,)

node: node-provision ## Start node supervisor (auto-provisions node/.env first; idempotent)
	uv run fleetent node start

kb-worker: ## Start the KB ingest worker (single queue consumer)
	uv run fleetent kb-worker

agent: ## Run one agent directly with HTTP /chat+/ws: make agent AGENT=<name> [AGENT_PORT=8766]
	@test -n "$(AGENT)" || { echo "usage: make agent AGENT=<name> [AGENT_PORT=8766]"; exit 2; }
	uv run fleetent agent run "$(AGENT)" --home "$(FLEETENT_HOME)/tenants/default/agents/$(AGENT)" --port $(AGENT_PORT)

# NOTE: the default URL targets AGENT_PORT, which only matches an agent started via
# `make agent`. Node-managed agents (`make node`) listen on a random loopback port
# allocated per spawn — pass URL=ws://127.0.0.1:<that-port>/ws explicitly for those.
chat: ## Connect the terminal TUI to an agent: make chat TOKEN=<tui-token> [URL=ws://...]
	@test -n "$(TOKEN)" || { echo "usage: make chat TOKEN=<tui-token> [URL=ws://...]"; exit 2; }
	uv run fleetent chat --url "$(or $(URL),ws://127.0.0.1:$(AGENT_PORT)/ws)" --token "$(TOKEN)"

dev-clean: ## Remove the entire dev home (.fleetent-dev by default)
	rm -rf "$(FLEETENT_HOME)"
