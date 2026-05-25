## Purpose

Defines agent configurations (system prompt, tool allowlist) stored in SQLite, supports user-to-agent assignment, and controls which tools an agent can access via glob patterns.
## Requirements
### Requirement: Agent definition storage
The system SHALL store agent definitions (name, system_prompt, allowed_tools) in the `agents` SQLite table.

#### Scenario: Create agent
- **WHEN** admin CLI calls `create-agent --name "assistant" --system-prompt "..." --allowed-tools '["shell","github__*"]'`
- **THEN** a row is inserted into `agents` with the given fields

#### Scenario: Query agent by name
- **WHEN** an incoming message is associated with an agent named "assistant"
- **THEN** `agent_store.get_by_name("assistant")` returns the full agent definition

### Requirement: User-to-agent assignment
The system SHALL support assigning one or more agents to a user via the `user_agents` table.

#### Scenario: User assigned to agent
- **WHEN** admin assigns user `user_id=X` to agent `agent_id=1`
- **THEN** a row exists in `user_agents(user_id=X, agent_id=1)`

#### Scenario: Look up user's agent
- **WHEN** a message arrives from `user_id=X`
- **THEN** the system retrieves the agent assigned to that user to apply its `system_prompt` and `allowed_tools`

### Requirement: allowed_tools wildcard support
The `allowed_tools` field SHALL support glob-style wildcards for MCP server tools.

#### Scenario: Wildcard matches all tools from a server
- **WHEN** `allowed_tools = ["github__*"]`
- **THEN** any tool with prefix `github__` passes the access control check

#### Scenario: Exact match
- **WHEN** `allowed_tools = ["shell", "github__create_issue"]`
- **THEN** only `shell` and `github__create_issue` pass; `github__list_prs` is rejected

### Requirement: Schema
The `agents` table SHALL store: `id`, `name` (UNIQUE), `system_prompt`, `allowed_tools` (JSON array text), `created_at`.
The `user_agents` table SHALL store: `user_id` (→ users.id), `agent_id` (→ agents.id), with PRIMARY KEY on `(user_id, agent_id)`.

#### Scenario: Duplicate agent name rejected
- **WHEN** admin tries to create an agent with a name that already exists
- **THEN** the database UNIQUE constraint prevents it and an error is returned

### Requirement: Route configuration schema
`RouteConfig` defines the LLM routing parameters for a task type. It SHALL contain: `base_url`, `model`, `api_key_env`, `max_tokens`, and an optional `fallbacks` ordered sequence of model names to try when the primary model is unavailable.

#### Scenario: RouteConfig with fallbacks
- **WHEN** `RouteConfig` is instantiated with `fallbacks=("claude-haiku-4-5",)`
- **THEN** the config holds a valid fallback sequence accessible as `config.fallbacks`

#### Scenario: RouteConfig without fallbacks remains valid
- **WHEN** `RouteConfig` is instantiated without the `fallbacks` parameter
- **THEN** `config.fallbacks` is an empty tuple and the config is fully valid

