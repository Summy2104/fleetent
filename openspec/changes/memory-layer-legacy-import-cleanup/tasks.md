## 0. Proposal and boundaries

- [x] 0.1 Define proposal, design, tasks, and spec deltas before implementation
- [x] 0.2 Confirm no memory behavior change is in scope
- [x] 0.3 Confirm no schema, extraction prompt, vector namespace, retention, or compaction change is in scope
- [x] 0.4 Confirm module boundary impact is limited to canonical memory imports

## 1. Legacy memory import cleanup tests

- [ ] 1.1 Write failing tests: canonical memory package exports public API and `fleetent.memory_layer`
  raises `ModuleNotFoundError`
- [ ] 1.2 Verify red: run `uv run pytest tests/unit/test_memory_legacy_import_cleanup.py -x -q` and
  confirm failure because the legacy shim is still importable
- [ ] 1.3 Implement: delete `src/fleetent/memory_layer.py`
- [ ] 1.4 Implement: migrate source, tests, and evaluation imports to `fleetent.intelligence.memory`
- [ ] 1.5 Verify green: run `uv run pytest tests/unit/test_memory_legacy_import_cleanup.py -x -q`

## 2. Targeted behavior verification

- [ ] 2.1 Verify green: run memory package/import tests
- [ ] 2.2 Verify green: run memory retention/compaction tests
- [ ] 2.3 Verify green: run reflection and long-term context memory tests
- [ ] 2.4 Verify green: run evaluation import tests or targeted evaluation tests that touch memory imports

## 3. Docs, specs, and full gate

- [ ] 3.1 Implement: update architecture docs and spec deltas to remove legacy memory shim
  compatibility language; active specs update during archive
- [ ] 3.2 Verify green: run `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`
- [ ] 3.3 Verify green: run `uv run ruff format src tests`
- [ ] 3.4 Verify green: run `uv run ruff check src tests`
- [ ] 3.5 Verify green: run `uv run mypy src`
- [ ] 3.6 Verify green: run `uv run pytest -x -q`
- [ ] 3.7 Verify green: run `openspec validate memory-layer-legacy-import-cleanup --strict`
- [ ] 3.8 Verify green: run `git diff --check`
