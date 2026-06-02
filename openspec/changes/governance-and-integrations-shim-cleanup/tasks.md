## 0. Proposal and boundaries

- [x] 0.1 Define proposal, design, tasks, and spec deltas before implementation
- [x] 0.2 Confirm no database migration is needed
- [x] 0.3 Confirm no configuration namespace change is needed
- [x] 0.4 Confirm module boundary impact is limited to governance and integrations public imports

## 1. Legacy shim removal tests

- [ ] 1.1 Write failing tests: canonical governance/integrations imports remain available and deleted
  legacy modules raise `ModuleNotFoundError`
- [ ] 1.2 Verify red: run `uv run pytest tests/unit/test_legacy_shim_cleanup.py -x -q` and confirm
  failure because legacy modules still import
- [ ] 1.3 Implement: delete governance and integrations shim files
- [ ] 1.4 Implement: migrate source and tests to canonical import paths
- [ ] 1.5 Verify green: run `uv run pytest tests/unit/test_legacy_shim_cleanup.py -x -q`

## 2. Targeted behavior verification

- [ ] 2.1 Verify green: run governance-related unit/integration tests
- [ ] 2.2 Verify green: run integrations-related unit/integration tests
- [ ] 2.3 Verify green: run server/tools tests that use MCP and sandbox integrations

## 3. Docs, specs, and full gate

- [ ] 3.1 Implement: update active specs and architecture docs to remove legacy shim compatibility
  language
- [ ] 3.2 Verify green: run `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`
- [ ] 3.3 Verify green: run `uv run ruff format src tests`
- [ ] 3.4 Verify green: run `uv run ruff check src tests`
- [ ] 3.5 Verify green: run `uv run mypy src`
- [ ] 3.6 Verify green: run `uv run pytest -x -q`
- [ ] 3.7 Verify green: run `openspec validate governance-and-integrations-shim-cleanup --strict`
- [ ] 3.8 Verify green: run `git diff --check`
