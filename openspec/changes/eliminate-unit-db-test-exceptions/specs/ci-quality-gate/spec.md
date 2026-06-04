## ADDED Requirements

### Requirement: Unit test layer has no real database dependencies

`tests/unit/` SHALL NOT contain tests that create, migrate, query, or validate real database
state. SQLite-backed schema lifecycle, store CRUD, and DB runtime orchestration tests SHALL live
under `tests/integration/`.

#### Scenario: SQLite imports are integration-only
- **WHEN** a test imports `sqlite3` or calls `sqlite3.connect`
- **THEN** the test belongs under `tests/integration/`
- **AND** it SHALL NOT live under `tests/unit/`

#### Scenario: Production DB path mutation is integration-only
- **WHEN** a test monkeypatches or directly mutates production `DB_PATH` to point at a temporary DB
  file
- **THEN** the test belongs under `tests/integration/`
- **AND** it SHALL NOT live under `tests/unit/`

#### Scenario: Read-only compatibility assertions remain unit-eligible
- **WHEN** a test only asserts legacy re-export shims, public API import surface, or path constant
  values without creating, migrating, querying, or mutating a real database
- **THEN** the test MAY remain under `tests/unit/`
- **AND** the guard SHALL NOT fail it solely because it references a DB-related symbol name

#### Scenario: Store schema initialization is integration-only
- **WHEN** a test calls production `_init_db()` or validates table / column shape for a store
- **THEN** the test belongs under `tests/integration/`
- **AND** it SHALL NOT live under `tests/unit/`

#### Scenario: SQLite DATABASE_URL runtime is integration-only
- **WHEN** a test sets `DATABASE_URL` to `sqlite:///...` or creates a database runtime with a
  `sqlite:///...` URL to verify persistence behavior
- **THEN** the test belongs under `tests/integration/`
- **AND** it SHALL NOT live under `tests/unit/`

#### Scenario: Pure file fixtures remain allowed in unit tests
- **WHEN** a test uses `tmp_path` for pure file parsing, config path derivation, serialization, or
  an injected non-DB file boundary
- **THEN** the test MAY remain under `tests/unit/`
- **AND** the test SHALL NOT create or query a real database through that fixture

### Requirement: Legacy DB unit exceptions are eliminated

The test-layer guard SHALL no longer allow legacy SQLite / DB-backed tests to remain under
`tests/unit/`.

#### Scenario: Guard fails on DB-backed unit tests
- **WHEN** `uv run python scripts/check_test_layers.py` scans `tests/unit/`
- **THEN** it fails on DB-backed patterns including `sqlite3`, production `DB_PATH` mutation,
  production `_init_db()`, `DATABASE_URL=sqlite:///...`, and `create_database("sqlite:///...")`
- **AND** each diagnostic includes the file path, line number, and violated rule

#### Scenario: Guard has no DB legacy allowlist
- **WHEN** the guard uses an allowlist for temporary false positives
- **THEN** the allowlist SHALL NOT allow real SQLite / DB-backed unit tests
- **AND** any allowlist entry SHALL document a non-DB reason, such as a read-only compatibility
  assertion that does not create or query a database

#### Scenario: Existing DB-backed tests still run as integration tests
- **WHEN** DB-backed tests are migrated out of `tests/unit/`
- **THEN** equivalent tests remain collected under `tests/integration/`
- **AND** they continue to verify the same SQLite schema, store CRUD, or DB runtime behavior
