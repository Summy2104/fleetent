## ADDED Requirements

### Requirement: Per-agent MCP server binding storage

The system SHALL store per-agent MCP server bindings in an `agent_mcp_servers` table
keyed by `(agent_id, server_id)`, where `agent_id` references `agents.id` and
`server_id` is the MCP server identifier. Bindings are live (not part of the agent
version snapshot): creating or removing a binding SHALL NOT mint a new agent version.

#### Scenario: Bind an MCP server to an agent

- **WHEN** an MCP server "github" is bound to agent "support-bot"
- **THEN** a row `(support-bot.id, "github")` exists in `agent_mcp_servers`
- **AND** the agent's active version id is unchanged

#### Scenario: Unbind an MCP server

- **WHEN** the binding `(support-bot, "github")` is removed
- **THEN** no row for `(support-bot.id, "github")` remains in `agent_mcp_servers`

#### Scenario: Duplicate bind is idempotent

- **WHEN** "github" is bound to "support-bot" twice
- **THEN** exactly one `(support-bot.id, "github")` row exists

### Requirement: MCP bindings union into runtime tool filtering

At agent invocation the effective MCP server set SHALL be the union of the version
snapshot's `mcp_server_ids` and the agent's `agent_mcp_servers` bindings. Bindings
SHALL only add servers to the tool-schema filter; they SHALL NOT remove servers
present in the snapshot.

#### Scenario: Bound server tools become available

- **WHEN** agent "support-bot" has snapshot `mcp_server_ids=[]` and a binding to "github"
- **THEN** the tool schemas exposed to the model include the "github" MCP server's tools

#### Scenario: Snapshot servers are preserved

- **WHEN** the snapshot has `mcp_server_ids=["jira"]` and the agent is bound to "github"
- **THEN** the effective MCP set is `{"jira", "github"}`
