## Purpose

Defines agent configurations (system prompt, tool allowlist) stored in SQLite, supports user-to-agent assignment, and controls which tools an agent can access via glob patterns.
## Requirements
### Requirement: Agent definition storage
The system SHALL store agent definitions in the `agents` SQLite table with columns: `id`, `name` (UNIQUE), `system_prompt` (nullable; superseded by `agent_versions`), `allowed_tools` (nullable; superseded by `agent_versions`), `active_version_id` (→ `agent_versions.id`), `created_at`. Per-version mutable fields (system_prompt, allowed_tools, skills_dir, mcp_server_ids, model_overrides, memory_namespace) SHALL live in `agent_versions`. Archival/disable is handled by the existing `agent_admin_store` console state, not by a column on `agents`.

#### Scenario: Create agent persists agents + agent_versions in one transaction
- **WHEN** admin calls `create-agent --name "assistant" --system-prompt "..." --allowed-tools '["shell"]'`
- **THEN** one row is inserted into `agents` AND one row into `agent_versions` (version=1) inside a single transaction; `agents.active_version_id` references the new version row

#### Scenario: Query agent by name returns active version content
- **WHEN** an incoming message is associated with agent name `"assistant"` and `active_version_id` points to version 3
- **THEN** `agent_store.get_by_name("assistant")` returns a structure whose `system_prompt` and `allowed_tools` come from version 3's `agent_versions` row

### Requirement: User-to-agent assignment
The system SHALL support assigning one or more agents to a user via the `user_agents` table.

#### Scenario: User assigned via CLI
- **WHEN** admin runs `fleetent-admin assign-user --user-id <id> --agent-name <name>`
- **THEN** a row exists in `user_agents(user_id, agent_id)`

#### Scenario: User unassigned via CLI
- **WHEN** admin runs `fleetent-admin unassign-user --user-id <id> --agent-name <name>`
- **THEN** the matching row in `user_agents` is removed

#### Scenario: Look up user's agent resolves to active snapshot
- **WHEN** a message arrives from `user_id=X` who is bound to agent `agent_id=1`
- **THEN** the system retrieves the active `AgentSnapshot` for `agent_id=1` and applies its system_prompt, allowed_tools, skills_dir, mcp_server_ids, model_overrides, memory_namespace

### Requirement: allowed_tools wildcard support
The `allowed_tools` field SHALL support glob-style wildcards for MCP server tools, as before. MCP tool visibility is further constrained by the snapshot's `mcp_server_ids` allowlist; the tool must pass BOTH checks to appear in the schema.

#### Scenario: Wildcard matches all tools from an allowed MCP server
- **WHEN** `allowed_tools = ["github__*"]` AND `mcp_server_ids = ["github"]`
- **THEN** any tool with prefix `github__` passes

#### Scenario: Wildcard allowed but server not whitelisted
- **WHEN** `allowed_tools = ["github__*"]` AND `mcp_server_ids = []`
- **THEN** no `github__*` tool is offered to the LLM

### Requirement: Schema
The `agents` table SHALL store: `id`, `name` (UNIQUE), `system_prompt` (nullable), `allowed_tools` (nullable JSON array text), `active_version_id` (nullable, references `agent_versions(id)`), `created_at`.
The `user_agents` table SHALL store: `user_id` (→ users.id), `agent_id` (→ agents.id), with PRIMARY KEY on `(user_id, agent_id)`.

#### Scenario: Duplicate agent name rejected
- **WHEN** admin tries to create an agent with a name that already exists
- **THEN** the database UNIQUE constraint prevents it and an error is returned

#### Scenario: active_version_id references a version row
- **WHEN** an agent has been created
- **THEN** `agents.active_version_id` is non-null and references a row in `agent_versions` whose `agent_id` matches

### Requirement: Route configuration schema
`RouteConfig` defines the LLM routing parameters for a task type. It SHALL contain: `base_url`, `model`, `api_key_env`, `max_tokens`, and an optional `fallbacks` ordered sequence of model names to try when the primary model is unavailable.

#### Scenario: RouteConfig with fallbacks
- **WHEN** `RouteConfig` is instantiated with `fallbacks=("claude-haiku-4-5",)`
- **THEN** the config holds a valid fallback sequence accessible as `config.fallbacks`

#### Scenario: RouteConfig without fallbacks remains valid
- **WHEN** `RouteConfig` is instantiated without the `fallbacks` parameter
- **THEN** `config.fallbacks` is an empty tuple and the config is fully valid

