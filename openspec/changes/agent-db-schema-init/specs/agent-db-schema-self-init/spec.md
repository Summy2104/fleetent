# agent-db-schema-self-init Specification

## Purpose
standalone agent 进程（`fleetent agent run <id>`）启动时自动建立 agent DB（`agents/<id>/data/fleetent.db`）
所需的全部表结构，无需外部 alembic 步骤。每个 agent-side store 暴露幂等的 `ensure_schema()`
函数，由 `agent_app._start_infra()` 统一调用。

## Requirements

### Requirement: _start_infra initializes agent DB schema before any store access

`agent_app._start_infra()` SHALL call `_init_agent_db_schema()` as its first operation,
before session maintenance or any other infra initialization. `_init_agent_db_schema()`
SHALL create all agent-side tables in the DB pointed to by `DATABASE_URL`.

#### Scenario: Fresh agent DB gets all tables on first boot

- **WHEN** `fleetent agent run my-bot` starts with a fresh `agents/my-bot/data/fleetent.db`
- **THEN** after `_start_infra()` completes, the following tables SHALL exist:
  `traces`, `memory_items`, `reflection_reports`, `knowledge_bases`, `knowledge_documents`,
  `knowledge_chunks`, `chunks_fts`, `knowledge_source_states`

#### Scenario: Existing agent DB is unaffected (idempotent)

- **WHEN** `_init_agent_db_schema()` is called on a DB that already has all tables
- **THEN** no error is raised and no data is modified

### Requirement: Each agent-side store exposes ensure_schema

`traces.py`, `memory/store.py`, `reflection.py`, and `knowledge_base/operations.py` SHALL
each expose a public `ensure_schema(db: SQLiteDatabase) -> None` function that creates the
store's tables and indices using `CREATE TABLE IF NOT EXISTS` and
`CREATE INDEX IF NOT EXISTS`.

#### Scenario: ensure_schema creates tables idempotently

- **WHEN** `ensure_schema(db)` is called on an empty DB
- **THEN** the store's tables and indices are created

#### Scenario: ensure_schema is safe to call repeatedly

- **WHEN** `ensure_schema(db)` is called twice on the same DB
- **THEN** the second call does not raise an error
