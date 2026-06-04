## MODIFIED Requirements

### Requirement: Agent definition storage
The system SHALL store agent definitions in the `agents` SQLite table with columns: `id`, `name` (UNIQUE), `system_prompt` (nullable; superseded by `agent_versions`), `allowed_tools` (nullable; superseded by `agent_versions`), `active_version_id` (→ `agent_versions.id`), `created_at`. Per-version mutable fields (system_prompt, allowed_tools, skills_dir, mcp_server_ids, model_overrides, memory_namespace) SHALL live in `agent_versions`. Archival/disable is handled by the existing `agent_admin_store` console state, not by a column on `agents`. This storage is the **authoring** source of truth; runtime resolution is file-sourced (see "Runtime agent resolution is file-sourced") and SHALL NOT read these tables.

#### Scenario: Create agent persists agents + agent_versions in one transaction
- **WHEN** admin calls `create-agent --name "assistant" --system-prompt "..." --allowed-tools '["shell"]'`
- **THEN** one row is inserted into `agents` AND one row into `agent_versions` (version=1) inside a single transaction; `agents.active_version_id` references the new version row

#### Scenario: Query agent by name is an authoring/console read, not a runtime path
- **WHEN** the admin console or CLI looks up agent name `"assistant"` whose `active_version_id` points to version 3
- **THEN** `agent_store.get_by_name("assistant")` returns a structure whose `system_prompt` and `allowed_tools` come from version 3's `agent_versions` row
- **AND** this DB read serves authoring/console only; runtime message resolution does NOT use it (runtime is file-sourced)

## ADDED Requirements

### Requirement: Runtime agent resolution is file-sourced

At runtime the system SHALL resolve an agent's executable `AgentSnapshot` from its
self-contained file `config/agents/<name>/agent.yaml`, not from the
`agents`/`agent_versions` SQLite read path. The snapshot's runtime fields
(`system_prompt`, `allowed_tools`, `skills_dir`, `model_overrides`, `memory_namespace`)
SHALL come from the file, and the agent's runtime identity SHALL be its `name`. The DB
authoring requirements (creating `agents`/`agent_versions` rows via the admin console
and CLI) are unchanged; the file is the runtime artifact generated from them.

#### Scenario: Active snapshot resolved from file, not DB

- **WHEN** a message is routed to agent `assistant` and `config/agents/assistant/agent.yaml` exists
- **THEN** the applied `AgentSnapshot` (system_prompt, allowed_tools, skills_dir,
  model_overrides, memory_namespace) is read from that file and identified by the name
  `assistant`, with no `agents`/`agent_versions` read

#### Scenario: Missing agent file resolves to nothing

- **WHEN** routing references agent name `ghost` but no `config/agents/ghost/agent.yaml` exists
- **THEN** runtime resolution returns no snapshot and the request proceeds as a bare run
