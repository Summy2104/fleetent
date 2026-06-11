## MODIFIED Requirements

### Requirement: Scheduled task definition and persistence
The system SHALL store scheduled task definitions in an **agent-side** SQLite `scheduled_tasks` table whose schema is owned by the per-agent `agent_state.db` unified embedded forward-only migrations (`AGENT_STATE_MIGRATIONS`, with `PRAGMA user_version` + migrate-on-open), NOT by `schedule_store` self-init and NOT by Alembic and NOT in the platform database (the management-DB table is dropped; `scheduled_tasks` is a pure agent-side table living in the same `agent_state.db` as `traces`/`reflection_reports`/`memory_items`/`approvals`). `schedule_store` SHALL access the table through a database injected via `schedule_store.set_state_db(db)` (the same `agent_scope`-resolved `agent_state.db` handle injected into the other agent-side stores at boot); `schedule_store` SHALL NOT expose an `ensure_schema()` entry point and SHALL NOT resolve `DATABASE_URL` to self-connect. All SQL SHALL use named parameters. Each task SHALL have: `id` (UUID), `name`, `schedule_kind` (`cron`/`once`/`interval`), the kind's schedule fields (`cron_expr` for cron, `run_at` for once, `interval_seconds` + optional `anchor` for interval), `timezone`, `user_id`, `message` (prompt text), optional `session_id`, `origin` (creation-context JSON), optional `deliver` (delivery-target JSON), `enabled` flag, `source` (`static`/`dynamic`/`tool`), `created_at`, and runtime-state columns `last_run_at`, `last_status`, `last_error`, `next_run_at`. The `agent_name` column SHALL NOT exist (one agent per process).

#### Scenario: Task created and persisted in agent DB
- **WHEN** `schedule_store.create(name=..., schedule_kind="cron", cron_expr="0 9 * * 1-5", user_id=..., message=...)` is called against an injected `agent_state.db`
- **THEN** a new row appears in the agent-side `scheduled_tasks` with a generated UUID id and `enabled=True`

#### Scenario: Schema created by agent_state embedded migrations, without Alembic
- **WHEN** a fresh `agent_state.db` is opened with `AGENT_STATE_MIGRATIONS` and `schedule_store.set_state_db(db)` is injected
- **THEN** the `scheduled_tasks` table exists (created by the unified embedded `MIGRATIONS`) and `schedule_store` CRUD succeeds without any platform dependency and without `schedule_store.ensure_schema`

#### Scenario: Tasks listed
- **WHEN** `schedule_store.list_tasks()` is called
- **THEN** all enabled rows are returned as a list of dicts including `schedule_kind`, `origin`, `deliver`, and the runtime-state columns

#### Scenario: Task deleted
- **WHEN** `schedule_store.delete(task_id)` is called with an existing id
- **THEN** the row is removed from `scheduled_tasks`
