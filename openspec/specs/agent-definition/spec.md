## Purpose

Defines agent configurations (system prompt, tool allowlist) stored in SQLite, supports user-to-agent assignment, and controls which tools an agent can access via glob patterns.
## Requirements
### Requirement: Agent definition storage
The system SHALL store agent definitions (name, system_prompt, allowed_tools, plugins, allowed_skills) in the `agents` SQLite table. The `plugins` field is a list of plugin names (default empty) declaring which plugins the agent is authorized to use; it is persisted as a JSON array text, mirroring `allowed_tools`. The `allowed_skills` field is a list of skill names (default empty) that narrows which skills appear in the agent's `<available_skills>` catalog; it is persisted as a JSON array text, mirroring `allowed_tools`. An empty `allowed_skills` means no narrowing (all enabled skills remain visible, preserving existing behavior) — the opposite default semantics from `plugins`, because skills are visible to every agent by default whereas plugin tools are not.

#### Scenario: Create agent
- **WHEN** admin CLI calls `create-agent --name "assistant" --system-prompt "..." --allowed-tools '["shell","github__*"]'`
- **THEN** a row is inserted into `agents` with the given fields, and `plugins` and `allowed_skills` default to empty lists

#### Scenario: Create agent with plugins
- **WHEN** an agent is created with `plugins=["crm_tools"]`
- **THEN** the row stores `plugins` as `["crm_tools"]` and `get_by_name` reads it back unchanged

#### Scenario: Create agent with allowed_skills
- **WHEN** an agent is created with `allowed_skills=["weather"]`
- **THEN** the row stores `allowed_skills` as `["weather"]` and `get_by_name` reads it back unchanged

#### Scenario: Query agent by name
- **WHEN** an incoming message is associated with an agent named "assistant"
- **THEN** `agent_store.get_by_name("assistant")` returns the full agent definition including its `plugins` and `allowed_skills` lists

#### Scenario: Legacy row without plugins
- **WHEN** an existing `agents` row predates the `plugins` column
- **THEN** reading that agent yields `plugins == []` (backward compatible, no behavior change)

#### Scenario: Legacy row without allowed_skills
- **WHEN** an existing `agents` row predates the `allowed_skills` column
- **THEN** reading that agent yields `allowed_skills == []` (backward compatible: empty means no narrowing, all enabled skills visible)

### Requirement: User-to-agent assignment
The system SHALL support assigning one or more agents to a user via the `user_agents` table.

#### Scenario: User assigned to agent
- **WHEN** admin assigns user `user_id=X` to agent `agent_id=1`
- **THEN** a row exists in `user_agents(user_id=X, agent_id=1)`

#### Scenario: Look up user's agent
- **WHEN** a message arrives from `user_id=X`
- **THEN** the system retrieves the agent assigned to that user to apply its `system_prompt` and `allowed_tools`

### Requirement: allowed_tools wildcard support
The `allowed_tools` field SHALL support glob-style wildcards for MCP server tools and plugin tools. An agent's authorized plugins SHALL be expanded into namespace wildcard patterns `{plugin_name}__*` and merged into the effective `allowed_tools` used for the access control check, so that a plugin tool is exposed to the agent only when its plugin is listed in the agent's `plugins`.

#### Scenario: Wildcard matches all tools from a server
- **WHEN** `allowed_tools = ["github__*"]`
- **THEN** any tool with prefix `github__` passes the access control check

#### Scenario: Exact match
- **WHEN** `allowed_tools = ["shell", "github__create_issue"]`
- **THEN** only `shell` and `github__create_issue` pass; `github__list_prs` is rejected

#### Scenario: Authorized plugin expands to namespace wildcard
- **WHEN** an agent's `plugins` contains `crm_tools`
- **THEN** `crm_tools__*` is merged into the effective `allowed_tools`, so `crm_tools__lookup` passes the access control check and is exposed to the LLM

#### Scenario: Unauthorized plugin tool is not exposed
- **WHEN** an agent's `plugins` does not contain `crm_tools`
- **THEN** no `crm_tools__*` pattern is present, so `crm_tools__lookup` fails the access control check and does not appear in the tool schemas exposed to the LLM

### Requirement: Schema
The `agents` table SHALL store: `id`, `name` (UNIQUE), `system_prompt`, `allowed_tools` (JSON array text), `plugins` (JSON array text, default `[]`), `allowed_skills` (JSON array text, default `[]`), `created_at`.
The `user_agents` table SHALL store: `user_id` (→ users.id), `agent_id` (→ agents.id), with PRIMARY KEY on `(user_id, agent_id)`.

#### Scenario: Duplicate agent name rejected
- **WHEN** admin tries to create an agent with a name that already exists
- **THEN** the database UNIQUE constraint prevents it and an error is returned

#### Scenario: Plugins column defaults for existing rows
- **WHEN** the `plugins` column is added to a table that already contains agent rows
- **THEN** existing rows take the `[]` default and remain readable without error

#### Scenario: allowed_skills column defaults for existing rows
- **WHEN** the `allowed_skills` column is added (alembic 004) to a table that already contains agent rows
- **THEN** existing rows take the `[]` default and remain readable without error

### Requirement: Route configuration schema
`RouteConfig` defines the LLM routing parameters for a task type. It SHALL contain: `base_url`, `model`, `api_key_env`, `max_tokens`, and an optional `fallbacks` ordered sequence of model names to try when the primary model is unavailable.

#### Scenario: RouteConfig with fallbacks
- **WHEN** `RouteConfig` is instantiated with `fallbacks=("claude-haiku-4-5",)`
- **THEN** the config holds a valid fallback sequence accessible as `config.fallbacks`

#### Scenario: RouteConfig without fallbacks remains valid
- **WHEN** `RouteConfig` is instantiated without the `fallbacks` parameter
- **THEN** `config.fallbacks` is an empty tuple and the config is fully valid

