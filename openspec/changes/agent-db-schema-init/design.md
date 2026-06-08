## Context

`per-agent-data-isolation` (PR #190) redirects `DATABASE_URL` to
`agents/<id>/data/fleetent.db` in `agent_app.boot()` via `_redirect_agent_data_paths()`.
Every agent-side store (`traces`, `memory`, `reflection`, KB) calls `create_database(DATABASE_URL)`
at first use — `SQLiteDatabase.execute()` auto-creates the parent directory but not the tables.
The result is `sqlite3.OperationalError: no such table` on first write.

The install script currently runs `alembic upgrade head` targeting the global
`$FLEETENT_HOME/data/fleetent.db`, creating migrations 001-009. After the isolation change,
the per-agent DB at `agents/<id>/data/fleetent.db` is never touched by alembic.

All agent-side stores resolve their DB via `os.environ.get("DATABASE_URL", ...)` or
`Settings().database_url` — both read the same env var that `_redirect_agent_data_paths`
sets. The `user_store` uses an independent `DB_PATH` constant and is unaffected.

## Goals / Non-Goals

**Goals**
- Every `fleetent agent run` process can write traces, memory, reflection, and KB on
  first use without any manual alembic step
- Schema initialization is idempotent and transparent (a no-op if tables already exist)
- Platform tables (migrations 001-002) remain under alembic management, unaffected

**Non-Goals**
- Schema migration/upgrade between versions (ALTER TABLE) — out of scope for this change;
  handled later with try/except ALTER if needed
- Removing the alembic dependency from the project entirely

## Decisions

**D1 — `ensure_schema()` per store, orchestrated from `_start_infra()`**

Each store exposes a public `ensure_schema(db: SQLiteDatabase) -> None`. A single
`_init_agent_db_schema()` function in `agent_app` calls `create_database(DATABASE_URL)`
once and passes it to all store `ensure_schema` functions. Called as the first line of
`_start_infra()`, before session maintenance or any other infra.

Alternative: lazy ensure per call-site (inside `append_trace`, etc.). Rejected: repeated
overhead on every call even though it's cheap; less explicit about when initialization runs.

**D2 — DDL transcribed from migrations, NOT imported from alembic**

`ensure_schema` functions contain plain `CREATE TABLE IF NOT EXISTS` DDL matching the
migration DDL exactly. Alembic is not called at runtime; the migrations remain the
authoritative record of schema history but are not a runtime dependency.

`CREATE INDEX IF NOT EXISTS` is used for indexes (SQLite supports this syntax).

**D3 — FTS5 virtual table (`chunks_fts`) uses `CREATE VIRTUAL TABLE IF NOT EXISTS`**

Migration 008 creates a FTS5 virtual table. SQLite supports
`CREATE VIRTUAL TABLE IF NOT EXISTS` since 3.7.0, which is safe to use.

**D4 — KB `ensure_schema` lives in `operations.py`**

The KB schema spans four migrations (006-009) and all KB DB operations funnel through
`operations.py`. Centralizing KB `ensure_schema` there avoids spreading DDL across
multiple KB sub-modules.

## Risks / Trade-offs

- **DDL drift**: if a future migration adds a column, `ensure_schema` must be updated in
  sync. Mitigation: add a comment in `ensure_schema` referencing the migration revision.
- **ALTER TABLE not handled**: existing agents that were deployed BEFORE the per-agent
  isolation (when tables were in the global DB) and are now being upgraded may have stale
  table schemas if columns were added. Mitigation: those agents are starting fresh anyway
  since the DB path changed; old data is in the global DB.

## Migration Plan

No data migration needed. Existing agents that had data in `$FLEETENT_HOME/data/fleetent.db`
continue to have it there (untouched). New per-agent DBs start fresh with full schema.

The install script's `init_db()` is unchanged — it migrates the global DB for platform
use (migrations 001-002 create platform tables).
