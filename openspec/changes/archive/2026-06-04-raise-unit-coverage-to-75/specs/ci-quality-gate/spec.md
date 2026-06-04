## ADDED Requirements

### Requirement: Repository unit coverage gate stays at 75 percent

The repository SHALL keep a unit-test coverage gate that measures `tests/unit/` against
`src/fleetent` and fails below 75% total coverage.

#### Scenario: Unit coverage command remains scoped to unit tests
- **WHEN** the CI unit coverage target runs
- **THEN** it runs coverage with `--source=src/fleetent`
- **AND** it collects tests from `tests/unit`
- **AND** it reports coverage with `--fail-under=75`

#### Scenario: Coverage scope is not weakened
- **WHEN** this coverage-improvement change is implemented
- **THEN** it SHALL NOT lower the coverage threshold below 75%
- **AND** it SHALL NOT add omit rules to remove low-coverage production modules from measurement
- **AND** it SHALL NOT narrow the measured source below `src/fleetent`

### Requirement: Unit coverage is improved through layered unit tests

The repository SHALL raise total unit coverage for `src/fleetent` to at least 75% by adding
meaningful unit tests that respect the established test-layer boundaries.

#### Scenario: Unit coverage passes the CI gate
- **WHEN** `make test-unit-ci` runs after this change
- **THEN** all unit tests pass
- **AND** total coverage for `src/fleetent` is at least 75%

#### Scenario: New coverage tests remain unit-layer compliant
- **WHEN** new tests are added to improve coverage
- **THEN** they SHALL mock or fake external DB, HTTP, LLM, sandbox, MCP, filesystem, and provider
  boundaries as needed
- **AND** they SHALL NOT use real SQLite persistence, Alembic migrations, FastAPI app lifespan,
  external services, or multi-module runtime orchestration in `tests/unit/`

#### Scenario: Integration-only behavior is not used to satisfy unit coverage
- **WHEN** behavior requires real database state, migrated schema, HTTP app routing through
  `TestClient`, or runtime orchestration across multiple modules
- **THEN** it remains under `tests/integration/`
- **AND** it SHALL NOT be moved into `tests/unit/` to increase unit coverage
