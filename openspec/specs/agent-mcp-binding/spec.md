# agent-mcp-binding Specification

## Purpose
TBD - created by syncing change expand-agent-bindings. Update Purpose after archive.
## Requirements
### Requirement: Per-agent MCP server binding storage

The system SHALL store per-agent MCP server bindings in an `agent_mcp_servers` table
keyed by `(agent_id, server_id)`, where `agent_id` references `agents.id` and
`server_id` is the MCP server identifier. `agent_mcp_servers` SHALL be the single
source of truth for an agent's MCP server mounts: there SHALL NOT be any version-snapshot
JSON representation (`agent_versions.mcp_server_ids`) or any other parallel mount list.
Creating or removing a binding SHALL be a direct relational write to `agent_mcp_servers`
and SHALL NOT mint any agent version.

#### Scenario: Bind an MCP server to an agent

- **WHEN** an MCP server "github" is bound to agent "support-bot"
- **THEN** a row `(support-bot.id, "github")` exists in `agent_mcp_servers`
- **AND** no MCP mount representation for the agent exists outside `agent_mcp_servers`

#### Scenario: Unbind an MCP server

- **WHEN** the binding `(support-bot, "github")` is removed
- **THEN** no row for `(support-bot.id, "github")` remains in `agent_mcp_servers`

#### Scenario: Duplicate bind is idempotent

- **WHEN** "github" is bound to "support-bot" twice
- **THEN** exactly one `(support-bot.id, "github")` row exists

### Requirement: MCP bindings union into runtime tool filtering

At agent invocation the effective MCP server set SHALL be exactly the agent's
`agent_mcp_servers` bindings, read directly from the relational table. There SHALL be
no version-snapshot `mcp_server_ids` source to merge: the prior union of snapshot JSON
and bindings is removed, and `agent_mcp_servers` is the sole input to the MCP tool-schema
filter.

#### Scenario: Bound server tools become available

- **WHEN** agent "support-bot" is bound to "github" in `agent_mcp_servers`
- **THEN** the tool schemas exposed to the model include the "github" MCP server's tools

#### Scenario: All bound servers are exposed

- **WHEN** agent "support-bot" is bound to "jira" and "github" in `agent_mcp_servers`
- **THEN** the effective MCP set is `{"jira", "github"}`

