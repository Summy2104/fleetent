## MODIFIED Requirements

### Requirement: Per-agent data directory at boot

`agent_app.boot()` SHALL redirect all per-agent runtime data sinks to `home_dir/data/`
immediately after `home_dir` is resolved and before any infrastructure initialisation.
The redirection SHALL cover sessions, database, IM approvals, diagnostics, and log directory.
After redirection, `_start_infra()` SHALL initialize the agent DB schema so that all
agent-side tables exist before any store operation. Agent runtime tables MUST be reached via
the per-agent state DB (`agent_scope` → `agent_state.db`) through the unified `db.py` boundary;
no agent runtime table may be written through a global `DB_PATH` + raw `sqlite3.connect`.

#### Scenario: Sessions land in agent home

- **WHEN** `fleetent agent run my-bot` starts
- **THEN** `session.manager.SESSIONS_DIR` SHALL equal `~/.fleetent/agents/my-bot/data/sessions/`
- **AND** all new session files SHALL be written to that directory

#### Scenario: DB lands in agent home

- **WHEN** `fleetent agent run my-bot` starts and `DATABASE_URL` is not set in environment
- **THEN** the default SQLite database SHALL be at `~/.fleetent/agents/my-bot/data/fleetent.db`

#### Scenario: Agent DB tables exist after boot

- **WHEN** `fleetent agent run my-bot` completes `_start_infra()`
- **THEN** `agents/my-bot/data/fleetent.db` SHALL contain all agent-side tables
  (`traces`, `memory_items`, `reflection_reports`, `session_anti_flap`, `sub_agent_runs`,
  `memory_maintenance_proposals`, `skill_proposals`, knowledge base tables)

#### Scenario: IM approvals land in agent home

- **WHEN** `fleetent agent run my-bot` starts
- **THEN** `im_gateway.access.APPROVALS_PATH` SHALL equal
  `~/.fleetent/agents/my-bot/data/im_approvals.json`

#### Scenario: Explicit DATABASE_URL is respected

- **WHEN** `DATABASE_URL` is set in the agent's `.env` or system environment
- **THEN** the database SHALL use that URL regardless of the agent home
- **AND** `agent_app.boot()` SHALL NOT override an explicit `DATABASE_URL`
