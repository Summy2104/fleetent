## MODIFIED Requirements

### Requirement: _start_infra initializes agent DB schema before any store access

`agent_app._start_infra()` SHALL call `_init_agent_db_schema()` as its first operation,
before session maintenance or any other infra initialization. `_init_agent_db_schema()`
SHALL bootstrap all agent-side tables by routing through `TenantRouter` anchored on the
agent's per-agent `data_dir` (`home_dir/data`), NOT by resolving `DATABASE_URL`: per-agent
runtime tables SHALL be created in `agent_state.db` via the unified `AGENT_STATE_MIGRATIONS`,
and tenant-scoped tables in `kb.db` / `shared_memory.db` via their embedded migrations.
The standalone agent process SHALL NOT create a `fleetent.db` file, and SHALL NOT require
`DATABASE_URL` to be set for agent-side schema bootstrap.

#### Scenario: Fresh agent DB gets all tables on first boot

- **WHEN** `fleetent agent run my-bot` starts with a fresh `agents/my-bot/data/` directory
- **THEN** after `_start_infra()` completes, the per-agent `agent_state.db` SHALL contain
  `sessions`, `traces`, `memory_items`, `reflection_reports`, `approvals`, `scheduled_tasks`,
  and the tenant-scoped `kb.db` SHALL contain
  `knowledge_bases`, `knowledge_documents`, `knowledge_chunks`, `chunks_fts`, `knowledge_source_states`

#### Scenario: No fleetent.db is created

- **WHEN** `fleetent agent run my-bot` completes `_start_infra()`
- **THEN** no `fleetent.db` file exists under the agent's `data/` directory
- **AND** `scheduled_tasks` lives in `agent_state.db`, not in a separate `DATABASE_URL`-resolved file

#### Scenario: Existing agent DB is unaffected (idempotent)

- **WHEN** `_init_agent_db_schema()` is called on a `data_dir` whose `agent_state.db` already has all tables
- **THEN** no error is raised and no data is modified
