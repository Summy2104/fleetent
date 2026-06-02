## 0. Proposal and boundaries

- [x] 0.1 Define proposal, design, tasks, and spec delta before implementation
- [x] 0.2 Confirm no admin command behavior change is in scope
- [x] 0.3 Confirm no database migration is needed
- [x] 0.4 Confirm no configuration namespace change is needed

## 1. Admin entrypoint cleanup tests

- [ ] 1.1 Write failing tests: `fleetent-admin` console script points to canonical admin CLI entrypoint
  and `fleetent.admin` raises `ModuleNotFoundError`
- [ ] 1.2 Verify red: run `uv run pytest tests/unit/test_admin_entrypoint_cleanup.py -x -q` and
  confirm failure because the legacy shim is still configured/importable
- [ ] 1.3 Implement: update `pyproject.toml` console script to
  `fleetent.platform.admin_cli.main:main`
- [ ] 1.4 Implement: delete `src/fleetent/admin.py`
- [ ] 1.5 Implement: migrate tests and docs to canonical admin CLI entrypoint
- [ ] 1.6 Verify green: run `uv run pytest tests/unit/test_admin_entrypoint_cleanup.py -x -q`

## 2. Behavior verification

- [ ] 2.1 Verify green: run `uv run pytest tests/integration/test_admin.py -x -q`
- [ ] 2.2 Verify green: run relevant packaging/import tests

## 3. Docs, specs, and full gate

- [ ] 3.1 Implement: update architecture docs and spec delta to remove legacy admin shim
  compatibility language; active specs update during archive
- [ ] 3.2 Verify green: run `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`
- [ ] 3.3 Verify green: run `uv run ruff format src tests`
- [ ] 3.4 Verify green: run `uv run ruff check src tests`
- [ ] 3.5 Verify green: run `uv run mypy src`
- [ ] 3.6 Verify green: run `uv run pytest -x -q`
- [ ] 3.7 Verify green: run `openspec validate admin-entrypoint-shim-cleanup --strict`
- [ ] 3.8 Verify green: run `git diff --check`
