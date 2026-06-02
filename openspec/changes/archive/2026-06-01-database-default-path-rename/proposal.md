## Why

The default SQLite database is still named `data/users.db`, but it now stores much more than users: API keys,
scheduling state, traces, memory, knowledge-base data, vector indexes, reflection reports, and other platform
tables. The name is misleading for operators and will make the upcoming upgrade / backup workflow harder to
explain.

This change renames the default application database path to `data/fleetent.db`. It intentionally does not add
automatic compatibility with the old path.

## What Changes

- Change the default `Settings.database_url` to `sqlite:///data/fleetent.db`.
- Change legacy `user_store.DB_PATH` default to `data/fleetent.db`.
- Change observability trace fallback database URL to `sqlite:///data/fleetent.db`.
- Change `alembic.ini` and `config/settings.yaml.example` defaults to `sqlite:///data/fleetent.db`.
- Update database-runtime / configuration specs and capability docs that describe the default database path.
- Update tests that assert the product default database path.

## Out of Scope

- No automatic migration, copy, rename, or fallback from `data/users.db`.
- No dual-read or compatibility shim for the old database filename.
- No backup / upgrade script.
- No PostgreSQL adapter.
- No legacy store migration to DB runtime.
- No data retention or log backup policy.

## Module Boundary Impact

- **Owning package**: `infrastructure` / database runtime.
- **Public API surface**: default configuration values only; no new public function.
- **Owned tables**: none.
- **Config namespace**: `database_url` default value.
- **Cross-module dependencies**: modules using default `Settings.database_url` or legacy `user_store.DB_PATH`
  will now point at `data/fleetent.db` unless explicitly configured.
- **Migration / shim plan**: no shim. Existing local data must be manually renamed from `data/users.db` to
  `data/fleetent.db` if the operator wants to preserve it.
