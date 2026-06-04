## Why

Bitbucket Pipelines runs `make test-unit-ci`, which measures `tests/unit/` coverage for
`src/fleetent` and fails below 75%. The current baseline is 67%:

- `uv run coverage run --source=src/fleetent -m pytest tests/unit -q`
- `uv run coverage report --sort=cover --skip-covered --show-missing`
- result: `TOTAL 16381 statements, 5370 missed, 67%`

The gap should be closed by adding meaningful unit tests, not by weakening the gate. This also
needs to stay compatible with the test-layer cleanup work: DB-backed persistence, FastAPI app
lifespan, Alembic, and multi-module runtime orchestration must not be moved into `tests/unit/`
just to inflate coverage.

## What Changes

- Add repository-level unit coverage requirements for `make test-unit-ci`.
- Add focused unit tests until total unit coverage for `src/fleetent` is at least 75%.
- Preserve the existing coverage command:
  - `coverage run --source=src/fleetent -m pytest tests/unit`
  - `coverage report --fail-under=75`
- Do not add `coverage omit`, do not narrow `--source`, and do not lower `--fail-under`.
- Prioritize high-ROI pure-unit surfaces:
  - memory extraction / maintenance / trends decisions
  - governance quota / alerting / blocklist / permission edge cases
  - provider connectivity and lightweight admin / CLI branch behavior with mocked dependencies
  - parser, normalization, validation, redaction, and error mapping branches
- Keep integration-only behavior in `tests/integration/`; use mocks/fakes for external DB, HTTP,
  LLM, sandbox, MCP, and filesystem boundaries in unit tests.

## Out of Scope

- Lowering the 75% coverage threshold.
- Changing `Makefile` coverage source, adding omit rules, or excluding low-coverage production
  files from measurement.
- Moving DB-backed, FastAPI lifespan, Alembic, real HTTP, real MCP, real sandbox, or runtime
  orchestration tests into `tests/unit/`.
- Refactoring production code solely to make coverage easier unless a small extraction is needed
  to test existing pure behavior without changing public contracts.
- Using integration, e2e, or evaluation coverage to satisfy this unit gate.

## Module Boundary Impact

- **Owning package**: `ci-quality-gate` / test suite governance.
- **Public API surface**: No new production public API is expected. If small helper extraction is
  unavoidable, it must remain inside the owning package and preserve existing imports.
- **Owned tables**: None.
- **Config namespace**: None.
- **Cross-module dependencies**: New unit tests may import public module APIs and patch external
  boundaries; they must not import package-internal implementations across module boundaries.
- **Migration / shim plan**: None. Legacy shim tests remain unit-eligible only when they are
  read-only compatibility checks.

## Impact

- **Tests**: Adds enough unit tests to raise repository unit coverage from 67% to at least 75%.
- **CI**: `make test-unit-ci` becomes green without weakening the existing gate.
- **Layering**: Unit coverage work continues to respect `tests/unit` versus `tests/integration`
  boundaries enforced by `scripts/check_test_layers.py`.
- **Verification**: Requires `make test-unit-ci`, unit tests, layer guard, ruff, mypy, full pytest,
  and OpenSpec validation before completion.
