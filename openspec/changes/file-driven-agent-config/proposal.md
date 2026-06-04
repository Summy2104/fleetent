## Why

At runtime an agent's identity, tools, skills, MCP servers, and channel/user
bindings are all resolved out of SQLite (`agents`/`agent_versions`/`channel_agents`/
`user_agents`). That couples every agent run to the database: an agent is not a
portable, self-contained unit, and "all agent config" is scattered across several
tables plus `Settings`/`routes.yaml`. We want an agent to be an **atom** — one
self-contained file that fully describes it and can run on its own — and we want the
runtime path to read that file with **zero database access**.

## What Changes

- Introduce a self-contained per-agent config file `config/agents/<name>/agent.yaml`
  (directory per agent, fixed filename; agent identity = directory name, validated
  against the in-file `name`). Env override `FLEETENT_AGENTS_DIR` (mirrors
  `FLEETENT_SKILLS_DIR`).
- The file fully describes the agent: `name`, `version` (corresponds to the DB
  version), `tenant_id`/`team_id`, `system_prompt`, `model_overrides`,
  `memory_namespace`, `skills_dir`, `allowed_skills`, `allowed_tools`, `plugins`,
  `features` (`code_execution`/`sandbox_env`), inline `mcp_servers`, and `bindings`
  (`default`/`channels`/`users`).
- Add a file loader + in-memory index (scanned at server startup like
  `skill_registry.scan()`, and per-call for CLI) that resolves an agent to the
  existing `AgentSnapshot` **without touching the database**.
- **Runtime resolution source migration (not externally breaking):**
  `runtime/snapshot.py` (`load_active`, `resolve_agent_for_request`,
  `resolve_mcp_servers`) reads from the file index instead of `agent_store`. The public
  function API is preserved and the `AgentSnapshot` runtime fields are unchanged, so
  `runtime/loop.py`, the IM normalizer, and tool filtering are unchanged. External agent
  behavior is unchanged; only the internal data source moves.
- Inline MCP: `mcp_server_ids` (DB lookup) becomes inline `mcp_servers` definitions;
  `resolve_mcp_servers` overlays them on the global defaults with no DB call.
- **`AgentSnapshot` identity changes type:** the `agent_id: int` field becomes a string
  identity holding the agent **name**, and `connector_scope` returns that string. This
  is the one `AgentSnapshot` shape change in this proposal.
- Secrets stay out of files: `mcp_servers`/connector definitions reference secrets by
  env-var name only (`api_key_env`/`credential_ref`); the scanner rejects inline
  plaintext secrets, reusing the existing secret-detection logic.

Out of scope (handled separately): the DB→file **export** step that generates
`agent.yaml`; the Web admin console + DB remain the authoring source of truth.
Historical-version resolution and version pinning stay on the DB/authoring side.
The connector-store and stats `agent_id`→name rekey is deferred to a follow-up.
Per-agent MCP and OAuth-connector DB admin (`mcp-server-admin`,
`agent-scoped-connectors`) remain authoring concerns; at runtime MCP comes from the
file's inline `mcp_servers`.

## Capabilities

### New Capabilities
- `file-agent-runtime`: the self-contained `agent.yaml` schema, the zero-DB file
  loader and in-memory index, file-based routing resolution (channel > user >
  default), inline MCP overlay, and secret rejection during scan.

### Modified Capabilities
- `agent-definition`: runtime agent resolution is sourced from
  `config/agents/<name>/agent.yaml` (identity by name) rather than the
  `agents`/`agent_versions` SQLite read path. DB authoring requirements are unchanged.
- `channel-agent-binding`: at runtime, channel→agent routing is resolved from the
  file index (`bindings.channels`) rather than the `channel_agents` table.
- `default-agent`: the default agent and the channel > user > default priority order
  are resolved from the file index rather than DB lookups.

## Impact

- **Code**: new `agent_config` loader/schema module; `runtime/snapshot.py` internals
  rewired to the file index; `config/agents/` directory convention +
  `FLEETENT_AGENTS_DIR`. `runtime/loop.py`, IM normalizer, and `filter_tool_schemas`
  unchanged (API/shape preserved).
- **Identity ripple**: `AgentSnapshot` identity and `connector_scope` become strings
  (the agent name). The OAuth-connector and stats DB tables are still keyed by int
  `agent_id`; their schema rekey to string keys is a deferred follow-up. OAuth-connector
  resolution (secrets in DB) is not on the zero-DB runtime path, so the deferred rekey
  does not block this change — the connector-store call site is adapted to the string
  identity (or short-circuited on the file path) here.
- **No new dependencies**; reuses `pydantic`/`pyyaml` and the existing
  `McpServerSettings` model and secret-detection logic.
- **Tests**: new unit + integration suites; runtime path asserts zero DB access.
