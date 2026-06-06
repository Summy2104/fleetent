# agent-scoped-connectors Specification

## Purpose
TBD - created by archiving change agent-scoped-oauth-mcp. Update Purpose after archive.
## Requirements
### Requirement: Connector ownership by agent
Each OAuth connector configuration SHALL carry an owning-agent dimension. A connector
row SHALL store an `agent_id` that is either a specific agent or null. A null
`agent_id` SHALL mean a global-default connector available to any agent that has no
agent-specific entry for the same connector id. The same connector id MAY exist once
per agent plus once as the global default.

#### Scenario: Agent-specific connector overrides global default
- **WHEN** a global-default `github` connector exists AND agent `billing` has its own
  `github` connector configuration
- **THEN** resolving the `github` connector for agent `billing` returns the
  `billing`-owned configuration, not the global default

#### Scenario: Falls back to global default
- **WHEN** a global-default `github` connector exists AND agent `sales` has no
  `github` connector of its own
- **THEN** resolving the `github` connector for agent `sales` returns the global-default
  configuration

#### Scenario: Unique per scope
- **WHEN** agent `billing` already owns a `github` connector
- **AND** an attempt is made to add a second `github` connector owned by `billing`
- **THEN** the store rejects the duplicate within that agent scope

### Requirement: Connector credential resolution is scoped by agent
OAuth credential and token resolution for a tool call SHALL be performed within the
owning-agent scope of the resolved connector. One agent's authorization SHALL NOT
satisfy a tool call made under a different agent scope. `client_secret` SHALL never be
persisted; per-agent secrets SHALL be referenced by per-scope environment variable
names.

#### Scenario: Authorization does not cross agents
- **WHEN** agent `billing` is authorized for its `github` connector
- **AND** agent `sales` has its own `github` connector that is not authorized
- **THEN** a `github` tool call made under agent `sales` is treated as not-authorized
  even though `billing` is authorized

#### Scenario: Secret never persisted
- **WHEN** a connector is created or edited with a `client_secret` field
- **THEN** the stored row contains no `client_secret` value

### Requirement: MCP server ownership by agent
MCP server definitions SHALL be resolvable per agent. The same `server_id` MAY have a
distinct definition (transport, endpoint/command, auth) per agent, plus an optional
global-default definition authored in Platform DB. Agent-specific
definitions SHALL override the global default for the same `server_id`.

#### Scenario: Per-agent server definition wins
- **WHEN** a global-default `github` MCP server is configured in Platform DB AND agent
  `billing` defines its own `github` MCP server
- **THEN** resolving MCP servers for agent `billing` uses the `billing`-owned `github`
  definition

#### Scenario: Global default used when agent has none
- **WHEN** agent `sales` defines no MCP servers of its own
- **THEN** resolving MCP servers for agent `sales` yields the global-default servers

### Requirement: MCP sessions and credentials isolated per agent
MCP tool dispatch SHALL key its connection/session by `(agent scope, server_id)` so two
agents using the same `server_id` never share a session or credential. An agent SHALL
only be able to dispatch MCP tools belonging to its own resolved servers.

#### Scenario: Two agents same server id get separate sessions
- **WHEN** agent `billing` and agent `sales` both resolve a `github` MCP server with
  different credentials
- **THEN** a tool dispatch under `billing` uses `billing`'s session/credential and a
  dispatch under `sales` uses `sales`'s session/credential; neither reuses the other

#### Scenario: Cross-agent MCP dispatch rejected
- **WHEN** agent `sales` has no `github` MCP server in its resolved scope
- **AND** a `github__create_issue` dispatch is attempted under agent `sales`
- **THEN** the dispatch is rejected and no global `github` session is used

### Requirement: Admin surfaces expose the owning agent
The admin face SHALL display the owning agent for each entry across the connector
directory, the per-user authorization matrix, and the MCP server list, and SHALL support
filtering by agent. Global-default entries SHALL be shown distinctly from agent-owned
entries.

#### Scenario: Filter connectors by agent
- **WHEN** an admin filters the connector directory by agent `billing`
- **THEN** only `billing`-owned connectors and applicable global defaults are listed,
  each labeled with its owning agent or "global default"

#### Scenario: MCP server list shows owner
- **WHEN** an admin opens the MCP server list
- **THEN** each server entry shows its owning agent, or "global default" for entries
  authored without an agent scope
