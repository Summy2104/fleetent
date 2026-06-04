## ADDED Requirements

### Requirement: Agent binding read endpoint

The agent admin API SHALL expose `GET /admin/agents/{name}/bindings` returning the
agent's current bindings: bound user ids, bound channels (each with `platform`,
`channel_id`, and `bound_version_id`), and bound MCP `server_id`s. Reads SHALL be
allowed for viewer and admin roles.

#### Scenario: Read an agent's bindings

- **WHEN** an admin or viewer sends `GET /admin/agents/{name}/bindings`
- **THEN** the response contains `users`, `channels`, and `mcp_servers` for that agent

#### Scenario: Unknown agent

- **WHEN** the agent name does not exist
- **THEN** the endpoint responds 404

### Requirement: Agent MCP binding endpoints

The agent admin API SHALL expose `POST /admin/agents/{name}/bindings/mcp/{server_id}`
and `DELETE /admin/agents/{name}/bindings/mcp/{server_id}` to bind and unbind an MCP
server for an agent. Writes SHALL require admin role and SHALL be audited. The POST
SHALL reject an unknown `server_id` (not present in `GET /admin/mcp/servers`) with 404.

#### Scenario: Bind a known MCP server

- **WHEN** an admin POSTs `/admin/agents/support-bot/bindings/mcp/github` and "github" is a known server
- **THEN** the binding is recorded and the action is audited

#### Scenario: Bind an unknown MCP server

- **WHEN** an admin POSTs `/admin/agents/support-bot/bindings/mcp/nope` and "nope" is not a known server
- **THEN** the endpoint responds 404 and no binding is recorded

#### Scenario: Viewer cannot bind

- **WHEN** a viewer attempts the POST or DELETE MCP binding route
- **THEN** the request is rejected as forbidden
