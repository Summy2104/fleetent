# agent-data-isolation Delta

## MODIFIED Requirements

### Requirement: Per-agent data directory at boot

`agent_app.boot()` SHALL redirect all per-agent runtime data sinks to `home_dir/data/`
immediately after `home_dir` is resolved and before any infrastructure initialisation.
The redirection SHALL cover sessions, database, IM approvals, diagnostics, and log directory.
After redirection, `_start_infra()` SHALL initialize the agent DB schema so that all
agent-side tables exist before any store operation. Agent runtime tables MUST be reached via
the per-agent state DB (`agent_scope` → `agent_state.db`) through the unified `db.py` boundary;
no agent runtime table may be written through a global `DB_PATH` + raw `sqlite3.connect`.
Boot SHALL NOT create `fleetent.db` and SHALL NOT read or set `DATABASE_URL`（standalone
agent 的运行数据一律经 `data_dir` 锚点路由到 per-agent / per-tenant 库文件）。

#### Scenario: Sessions land in agent home

- **WHEN** `fleetent agent run my-bot` starts
- **THEN** `session.manager.SESSIONS_DIR` SHALL equal `~/.fleetent/agents/my-bot/data/sessions/`
- **AND** all new session files SHALL be written to that directory

#### Scenario: DB lands in agent home

- **WHEN** `fleetent agent run my-bot` starts
- **THEN** the agent's runtime state SHALL be at the per-agent `agent_state.db` under the
  agent home data directory (resolved via `agent_scope`), and no `fleetent.db` SHALL be created

#### Scenario: Agent DB tables exist after boot

- **WHEN** `fleetent agent run my-bot` completes `_start_infra()`
- **THEN** the per-agent `agent_state.db` SHALL contain all agent-side tables
  (`sessions`, `traces`, `memory_items`, `approvals`, `approval_allowlist`,
  `reflection_reports`, `reflection_proposals`, `session_anti_flap`, `sub_agent_runs`,
  `budget_usage`, `scheduled_tasks`)
- **AND** knowledge base tables live in the per-tenant `kb.db` (embedded migrations), not in
  `agent_state.db`

#### Scenario: IM approvals land in agent home

- **WHEN** `fleetent agent run my-bot` starts
- **THEN** `im_gateway.access.APPROVALS_PATH` SHALL equal
  `~/.fleetent/agents/my-bot/data/im_approvals.json`
