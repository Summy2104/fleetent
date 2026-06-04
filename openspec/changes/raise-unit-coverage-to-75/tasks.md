## 0. Baseline And Targeting

- [x] 0.1 Record the current unit coverage baseline with
  `uv run coverage run --source=src/fleetent -m pytest tests/unit -q` and
  `uv run coverage report --sort=cover --skip-covered --show-missing`
- [x] 0.2 Identify high-ROI unit-test targets that can be covered without real DB, FastAPI
  lifespan, Alembic, external HTTP, MCP, sandbox, LLM, or multi-module runtime orchestration
- [x] 0.3 Confirm the implementation will not change coverage scope, coverage omit rules, or the
  `--fail-under=75` threshold

## 1. Coverage Gate Contract

- [x] 1.1 Write failing tests: add or update a unit contract test that verifies `Makefile`
  `test-unit-ci` still uses `coverage run --source=src/fleetent -m pytest tests/unit` and
  `coverage report --fail-under=75`
- [x] 1.2 Implement: adjust only docs or command wiring if needed, without lowering or bypassing
  the coverage gate
- [x] 1.3 Verify green: run the contract test

## 2. Pure Logic Coverage Batch 1

- [x] 2.1 Write failing tests: add focused unit tests for selected pure logic modules with low
  coverage, prioritizing deterministic parsing, validation, quota, alerting, redaction, or error
  mapping behavior
- [x] 2.2 Verify red: run the targeted new unit tests and confirm they fail for missing or
  unexercised expected behavior
- [x] 2.3 Implement: add only the minimal production changes needed to preserve existing behavior
  and make the tests pass; prefer no production changes when tests cover existing behavior
- [x] 2.4 Verify green: run the targeted unit tests

## 3. Mocked Boundary Coverage Batch 2

- [x] 3.1 Write failing tests: add focused unit tests for modules whose external dependencies can be
  mocked or faked, such as provider connectivity, lightweight admin / CLI handlers, filesystem
  boundary logic, or dependency error branches
- [x] 3.2 Verify red: run the targeted new unit tests and confirm they fail for missing or
  unexercised expected behavior
- [x] 3.3 Implement: patch external boundaries with mocks/fakes; do not introduce real DB, FastAPI
  lifespan, Alembic, external HTTP, MCP, sandbox, LLM, or runtime orchestration into unit tests
- [x] 3.4 Verify green: run the targeted unit tests

## 4. Coverage Closure

- [x] 4.1 Run `make test-unit-ci` and record the new total coverage
- [x] 4.2 If coverage remains below 75%, repeat a small TDD batch against the next highest-ROI
  pure-unit target until `make test-unit-ci` passes
- [x] 4.3 Run `uv run python scripts/check_test_layers.py` to confirm new tests did not violate
  unit/integration boundaries

## 5. Final Verification

- [x] 5.1 Run `uv run pytest tests/unit -x -q`
- [x] 5.2 Run `make test-unit-ci`
- [x] 5.3 Run `uv run python scripts/check_test_layers.py`
- [x] 5.4 Run `uv run ruff format src tests scripts`
- [x] 5.5 Run `uv run ruff check src tests scripts`
- [x] 5.6 Run `uv run mypy src`
- [x] 5.7 Run `uv run pytest -x -q`
- [x] 5.8 Run `openspec validate raise-unit-coverage-to-75 --strict`
- [x] 5.9 Run `git diff --check`

Execution notes:

- Baseline recorded: `1585 passed`, `TOTAL 16381 statements, 5372 missed, 67%`.
- Coverage targets selected from `coverage report --sort=cover --skip-covered --show-missing`:
  memory extraction/trends/shared/maintenance, reflection, admin/connector handlers, structured
  logging/startup diagnostics, vector backend helpers, platform maintenance, and resource
  collectors.
- Coverage gate contract red/green: temporary `--fail-under=76` assertion failed; restored to
  `--fail-under=75` and passed.
- Coverage closure: `make test-unit-ci` passed with `1620 passed` and `TOTAL 16381 statements,
  4150 missed, 75%`.
- Final verification passed: unit tests, coverage gate, test-layer guard, Ruff format/check, mypy,
  full pytest, OpenSpec strict validation, and diff whitespace check.
