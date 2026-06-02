## MODIFIED Requirements

### Requirement: Alembic migration management
The system SHALL use alembic to manage all database schema changes, with migration files checked into
the repository. Current migrations SHALL support the SQLite backend; new migration work SHALL avoid
assuming SQLite-only behavior unless explicitly documented. Each migration that creates or changes a
persistent table SHALL identify the module that owns that table, either in the migration
comment/docstring or in the corresponding OpenSpec change.

#### Scenario: Fresh install
- **WHEN** service starts on a new machine with no existing database
- **THEN** running `alembic upgrade head` creates all tables at the latest schema version

#### Scenario: Upgrade existing install
- **WHEN** a new version adds a table or column
- **THEN** running `alembic upgrade head` applies only the pending migrations without data loss

#### Scenario: Migration has module owner
- **WHEN** a migration creates or changes a persistent table
- **THEN** the migration or its OpenSpec change identifies the module that owns the table

### Requirement: No raw schema creation in application code
The system SHALL NOT use `CREATE TABLE IF NOT EXISTS` in application startup code for new tables.
New or migrated store modules SHALL rely on alembic-managed schema instead of store-local bootstrap
DDL. New tables SHALL be created through alembic migrations owned by the module responsible for the
data.

#### Scenario: New tables only created via migration
- **WHEN** the application starts
- **THEN** it does NOT call `CREATE TABLE` for new tables owned by migrated stores

#### Scenario: Existing users table
- **WHEN** alembic runs on a database with the legacy `users` table (created by `_init_db`)
- **THEN** migration treats it as already present and does not fail
