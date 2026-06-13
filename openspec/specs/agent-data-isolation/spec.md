# agent-data-isolation Specification

## Purpose
每个 standalone agent 进程（`fleetent agent run <id>`）的运行时数据（sessions、DB、logs、
diagnostics、IM approvals）写入该 agent 专属的 `agents/<id>/data/` 目录，而非共享的
`FLEETENT_HOME/data/`，实现 per-agent 数据完全隔离。

## Requirements

### Requirement: Per-agent data directory at boot

`agent_app.boot()` SHALL redirect all per-agent runtime data sinks to `home_dir/data/`
immediately after `home_dir` is resolved and before any infrastructure initialisation.
The redirection SHALL cover sessions, database, IM approvals, diagnostics, and log directory.
After redirection, `_start_infra()` SHALL initialize the agent DB schema so that all
agent-side tables exist before any store operation. Agent runtime tables MUST be reached via
the per-agent state DB (`agent_scope` → `agent_state.db`) through the unified `db.py` boundary;
no agent runtime table may be written through a global `DB_PATH` + raw `sqlite3.connect`.
Boot SHALL NOT create `fleetent.db` and SHALL NOT read or set `DATABASE_URL`.

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
  `scheduled_tasks`)
- **AND** knowledge base tables live in the per-tenant `kb.db` (embedded migrations), not in
  `agent_state.db`

#### Scenario: IM approvals land in agent home

- **WHEN** `fleetent agent run my-bot` starts
- **THEN** `im_gateway.access.APPROVALS_PATH` SHALL equal
  `~/.fleetent/agents/my-bot/data/im_approvals.json`

### Requirement: Log directory defaults to agent home

When `agent.observability.logging.directory` is blank or unset, the structured log sink
SHALL default to `home_dir/data/logs/`. A non-blank value SHALL be used as-is (absolute
or CWD-relative).

#### Scenario: Blank directory resolves to agent-home logs

- **WHEN** `agent.observability.logging.directory` is `""` (blank)
- **THEN** log files SHALL be written to `agents/<id>/data/logs/`

#### Scenario: Explicit directory overrides agent home

- **WHEN** `agent.observability.logging.directory` is set to `/var/log/my-bot`
- **THEN** log files SHALL be written to `/var/log/my-bot`
- **AND** the agent home data directory SHALL NOT be used for logs

### Requirement: Two-agent processes do not share data

Two concurrent `fleetent agent run` processes for different agents SHALL write to separate
data directories and SHALL NOT read each other's sessions or DB rows.

#### Scenario: Separate sessions per agent

- **WHEN** `fleetent agent run agent-a` and `fleetent agent run agent-b` both run
- **THEN** agent-a writes sessions to `agents/agent-a/data/sessions/`
- **AND** agent-b writes sessions to `agents/agent-b/data/sessions/`
- **AND** neither directory contains files from the other agent
