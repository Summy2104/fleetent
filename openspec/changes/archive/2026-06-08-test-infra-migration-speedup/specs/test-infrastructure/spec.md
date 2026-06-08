## ADDED Requirements

### Requirement: Cached migrated-database helper for integration tests

Integration tests that need a migrated SQLite database MUST obtain it through a single
shared helper that constructs the schema once per process and reuses it. The helper
SHALL run the real Alembic `upgrade head` exactly once into a template database, then
materialize each requested database by copying that template. Each test MUST still
receive its own database file so per-test isolation is preserved.

#### Scenario: First call builds the template via real migrations

- **WHEN** the shared `apply_migrations(db_path)` helper is called for the first time in a process
- **THEN** the real Alembic `upgrade head` runs once to produce a template database
- **AND** the requested `db_path` is created with a schema byte-identical to a freshly migrated database

#### Scenario: Subsequent calls copy the cached template

- **WHEN** the shared helper is called again in the same process
- **THEN** it materializes the database by copying the cached template instead of re-running migrations
- **AND** each caller receives a distinct database file that can be mutated without affecting other tests

#### Scenario: Migration-logic tests are unaffected

- **WHEN** a test exercises migration behavior itself (step-wise upgrade/downgrade to a specific revision)
- **THEN** it continues to invoke Alembic directly rather than the cached helper

### Requirement: Unit tests stay free of database-backed patterns

Tests under `tests/unit` MUST NOT embed a `sqlite:///` `DATABASE_URL`, as enforced by
`scripts/check_test_layers.py`. Tests that only verify configuration or environment
precedence (and never open a database) SHALL express their values with a non-database
scheme so the layer gate passes.

#### Scenario: Layer gate passes on a clean unit suite

- **WHEN** `scripts/check_test_layers.py` scans `tests/unit`
- **THEN** it reports no `sqlite-database-url` violations and exits with status 0

#### Scenario: Precedence-only tests avoid sqlite URLs

- **WHEN** a unit test asserts config/env `DATABASE_URL` precedence without opening a database
- **THEN** it uses a non-sqlite scheme value and its precedence assertions remain valid
