## ADDED Requirements

### Requirement: Unit test layer excludes integration dependencies

`tests/unit/` SHALL contain tests for single-module behavior with external dependencies mocked or
replaced by lightweight fakes. Tests that exercise FastAPI app lifespan, Alembic schema lifecycle,
SQLite-backed store/runtime orchestration, or multi-module runtime wiring SHALL live in
`tests/integration/`.

#### Scenario: FastAPI app lifespan tests are integration tests
- **WHEN** a test uses FastAPI `TestClient`, enters application lifespan, or asserts HTTP endpoint
  behavior through the app object
- **THEN** the test belongs under `tests/integration/`
- **AND** it SHALL NOT live under `tests/unit/`

#### Scenario: Alembic and migration-backed database tests are integration tests
- **WHEN** a test runs Alembic migrations, imports migration helpers from `tests.integration.*`, or
  validates behavior against migrated SQLite tables
- **THEN** the test belongs under `tests/integration/`
- **AND** it SHALL NOT live under `tests/unit/`

#### Scenario: Unit tests may use lightweight file fixtures
- **WHEN** a test uses `tmp_path` for pure parsing, configuration path resolution, serialization, or
  an injected file boundary
- **THEN** the test MAY remain under `tests/unit/`
- **AND** it SHALL NOT validate real DB runtime orchestration through that file fixture

#### Scenario: Legacy SQLite store exceptions are explicit
- **WHEN** a legacy SQLite store test cannot be moved in this change without changing production
  boundaries
- **THEN** it MAY remain temporarily in `tests/unit/` only through an explicit test-layer guard
  allowlist entry
- **AND** the allowlist entry SHALL include the reason and the owning cleanup area

### Requirement: Test layer guard prevents new unit/integration drift

The repository SHALL provide a guard command that scans `tests/unit/` for disallowed integration
patterns and fails with actionable diagnostics.

#### Scenario: Guard detects integration-only imports and APIs
- **WHEN** `uv run python scripts/check_test_layers.py` scans `tests/unit/`
- **THEN** it fails if a unit test imports `fastapi.testclient.TestClient`, references `TestClient(`
  for app testing, imports from `tests.integration.*`, calls `apply_migrations`, or runs Alembic
  `command.upgrade`
- **AND** the diagnostic includes file path, line number, and the violated rule

#### Scenario: Guard passes after approved migration
- **WHEN** high-confidence misplaced tests have been moved to `tests/integration/`
- **AND** any temporary legacy exceptions are captured in the guard allowlist
- **THEN** `uv run python scripts/check_test_layers.py` exits successfully

#### Scenario: Project guidance documents the executable boundary
- **WHEN** a developer or AI agent reads project testing guidance
- **THEN** the guidance describes the unit/integration boundary using the same rules enforced by
  `scripts/check_test_layers.py`
- **AND** it tells contributors to run the guard before completing test-suite organization work
