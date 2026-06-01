## Why

Fleetent now relies on a single SQLite application database for users, traces, memory, knowledge-base data,
vector indexes, scheduling, and other runtime state. Before on-prem operators run Alembic migrations during an
upgrade, they need a repeatable way to create a restorable backup and fail safely if migration does not
complete.

This change adds a minimal upgrade script for the SQLite-first MVP. It depends on `database-default-path-rename`
so the default database path is `data/fleetent.db`.

## What Changes

- Add `scripts/upgrade.py` as the supported local upgrade entry point.
- Resolve the effective database URL from `--database-url`, `DATABASE_URL`, or `Settings().database_url`.
- Allow `--backup-dir` to override the default `data/backups` directory for tests and custom deployments.
- Support only local SQLite database URLs and fail fast for unsupported backends.
- Create a timestamped backup under `data/backups/YYYYMMDD-HHMMSS/fleetent.db` before running migrations.
- Run `alembic upgrade head` after a successful backup.
- Support `--dry-run` to validate the database URL and print planned actions without requiring the DB file to
  exist, writing backup files, or running migrations.
- Support `--backup-only` to create a backup without running migrations.
- Return a non-zero exit code if backup or migration fails.
- Document manual restore steps: stop service, replace database file from backup, restart service.
- Update deployment docs and roadmap.

## Out of Scope

- No complete on-prem install package.
- No Docker release automation or image publishing workflow.
- No automatic rollback after migration failure.
- No PostgreSQL backup or restore support.
- No license key behavior.
- No log / trace retention policy.
- No Admin UI, HTTP API, scheduler, or background worker.
- No automatic upgrade trigger during application startup.

## Module Boundary Impact

- **Owning package**: deployment / infrastructure scripts.
- **Public API surface**: `scripts/upgrade.py` CLI only; no importable runtime API.
- **Owned tables**: none.
- **Config namespace**: reads existing `database_url`; no new config field.
- **Cross-module dependencies**: uses configuration defaults and Alembic migrations; does not import business
  modules or mutate module-owned data directly.
- **Migration / shim plan**: depends on `database-default-path-rename`; no users.db compatibility path.
