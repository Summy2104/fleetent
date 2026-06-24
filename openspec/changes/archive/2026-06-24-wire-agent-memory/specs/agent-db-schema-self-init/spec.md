## MODIFIED Requirements

### Requirement: _start_infra initializes agent DB schema before any store access

`agent_app._start_infra()` SHALL call `_init_agent_db_schema()` as its first operation,
before session maintenance or any other infra initialization. `_init_agent_db_schema()`
SHALL bootstrap all agent-side tables by routing through `TenantRouter` anchored on the
agent's per-agent `data_dir` (`home_dir/data`), NOT by resolving `DATABASE_URL`: per-agent
runtime tables — including `agent_memory_items` — SHALL be created in `agent_state.db` via
the unified `AGENT_STATE_MIGRATIONS` (resolved via `agent_scope(tenant, agent_id)`); the
tenant-scoped `kb.db` is created via its embedded migrations. **Agent memory is a per-agent
relational table inside `agent_state.db`, NOT a separate `agent_memory.db`**; there is no
`agent_memory.db` and no `shared_memory.db`. `agent_memory_items` SHALL NOT contain
`scope_type` / `scope_id` columns (agent isolation is provided by the per-agent physical DB).
The standalone agent process SHALL NOT create a `fleetent.db` file, and SHALL NOT require
`DATABASE_URL` to be set for agent-side schema bootstrap.

#### Scenario: Fresh agent DB gets all tables on first boot

- **WHEN** `fleetent agent run my-bot` starts with a fresh `agents/my-bot/data/` directory
- **THEN** after `_start_infra()` completes, the per-agent `agent_state.db` SHALL contain
  `sessions`, `traces`, `memory_items`, `agent_memory_items`, `reflection_reports`,
  `approval_requests`, `scheduled_tasks`
- **AND** the tenant-scoped `kb.db` SHALL contain
  `knowledge_bases`, `knowledge_documents`, `knowledge_chunks`, `chunks_fts`, `knowledge_source_states`

#### Scenario: No separate agent_memory.db / shared_memory.db

- **WHEN** `_init_agent_db_schema()` completes for an agent
- **THEN** no `agent_memory.db` and no `shared_memory.db` are created under the agent's `data/`
- **AND** agent memory relational rows live in `agent_state.db` (`agent_memory_items`); agent
  memory **vectors** remain in the separate `agent_memory_vectors.db` (`agentmem` vector family)

#### Scenario: No fleetent.db is created

- **WHEN** `fleetent agent run my-bot` completes `_start_infra()`
- **THEN** no `fleetent.db` file exists under the agent's `data/` directory

#### Scenario: Existing agent DB is unaffected (idempotent)

- **WHEN** `_init_agent_db_schema()` is called on a `data_dir` whose `agent_state.db` already has all tables
- **THEN** no error is raised and no data is modified
