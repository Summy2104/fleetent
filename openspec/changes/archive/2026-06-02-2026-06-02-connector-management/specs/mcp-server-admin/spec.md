## ADDED Requirements

### Requirement: MCP server list and connection status
The admin face SHALL list all configured MCP servers (stdio / HTTP transport) with a connection status aligned to the `mcp` domain: connected, startup-degraded (masked at startup), probe-failing-reconnecting (exponential backoff), and marked-permanently-unavailable. Each entry SHALL show registered tool count, the `server__{tool}` namespace list, and the last handshake/probe time. Connection state is delegated to the `mcp` domain and SHALL NOT be recomputed here.

#### Scenario: Startup-degraded server visible (场景 112)
- **WHEN** an admin opens the MCP server list while an HTTP MCP server was degraded after a failed startup handshake
- **THEN** that server shows "startup-degraded" with registered tool count 0, the rest of the platform is unaffected, and a "manual reconnect" action is available

#### Scenario: Connection states distinguished
- **WHEN** servers are respectively connected, reconnecting under backoff, and marked permanently unavailable
- **THEN** the list shows each distinct status as reported by the `mcp` domain

### Requirement: Registered tool namespace visibility
The admin face SHALL let an admin expand an MCP server to view its registered tools (name, description, input-schema summary). Tool names SHALL be shown under the `{server_id}__{tool_name}` (double-underscore) namespace so an admin can reference `server__*` tools when configuring an Agent's `allowed_tools`. Access control of the allowlist itself belongs to the `governance` domain; this face only makes tools visible.

#### Scenario: Tool namespace shown (场景 113)
- **WHEN** an admin expands a connected MCP server `github` that has registered tools
- **THEN** its tools are listed under the `github__{tool}` namespace for reference when configuring Agent `allowed_tools`

#### Scenario: Tool schema summary visible
- **WHEN** an admin expands a server's tool entry
- **THEN** the tool's name, description, and input-schema summary are shown

### Requirement: Manual reconnect and re-handshake
The admin face SHALL provide a "manual reconnect / re-handshake" action that triggers the `mcp` domain to re-attempt the handshake, and SHALL audit it. Connection failure / degradation SHALL NOT block platform startup; this face only presents status and triggers the action.

#### Scenario: Manual reconnect triggers handshake and audit
- **WHEN** an admin clicks "manual reconnect" on a degraded MCP server
- **THEN** the `mcp` domain re-attempts the handshake and the action is written to the audit log

#### Scenario: Reconnect requires admin
- **WHEN** a viewer attempts to trigger a manual reconnect or change an MCP server configuration
- **THEN** the request is rejected with 403

### Requirement: MCP doctor diagnostic entry
The admin face SHALL provide an entry to trigger the `mcp doctor` diagnostic and render its conclusions as a red/yellow/green checklist. Sensitive authentication values (tokens, API keys, credentials embedded in URLs) SHALL be masked.

#### Scenario: Doctor checklist masked
- **WHEN** an admin or viewer triggers the `mcp doctor` diagnostic
- **THEN** the result is rendered as a red/yellow/green checklist with all sensitive authentication values masked, never echoed in plaintext

### Requirement: MCP management permissions and audit
MCP server configuration changes and manual reconnects SHALL be admin-only; viewers MAY only browse the server list, connection status, and doctor conclusions. All write actions SHALL be written to the audit log (who, when, which server, what action).

#### Scenario: Viewer read-only on MCP face
- **WHEN** a viewer opens the MCP server list and doctor results
- **THEN** they can browse status and diagnostics but every write action (config change, manual reconnect) returns 403

#### Scenario: Unauthenticated rejected
- **WHEN** a request to any `/admin/mcp/*` endpoint carries no valid login session
- **THEN** the response is 401
