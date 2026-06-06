## ADDED Requirements

### Requirement: Per-server connect timeout

Connection-phase HTTP operations to an MCP server — the initialize/discovery requests, the admin connectivity probe, the background health probe, and the OAuth token request — SHALL use that server's configured connect timeout, defaulting to 10 seconds when not specified. The timeout SHALL be held per server, not as a single module-level constant.

#### Scenario: Configured connect timeout used for discovery
- **WHEN** an http MCP server is registered with a connect timeout of 5 seconds
- **THEN** the HTTP client used for its initialize/discovery requests is created with a 5 second timeout

#### Scenario: Default connect timeout when unspecified
- **WHEN** an http MCP server does not specify a connect timeout
- **THEN** its connection-phase HTTP operations use the 10 second default

### Requirement: Per-server call timeout

Tool-call HTTP operations to an MCP server SHALL use that server's configured call timeout, defaulting to 30 seconds when not specified. The timeout SHALL be held per server.

#### Scenario: Configured call timeout used for tool calls
- **WHEN** an http MCP server is configured with a call timeout of 90 seconds and a tool is invoked
- **THEN** the HTTP client used for the `tools/call` request is created with a 90 second timeout

#### Scenario: Default call timeout when unspecified
- **WHEN** an http MCP server does not specify a call timeout
- **THEN** its tool-call HTTP operations use the 30 second default

### Requirement: Timeouts configurable via agent configuration

An agent's `mcp_servers` entries SHALL be able to declare `connect_timeout` and/or `call_timeout`; when omitted, the defaults apply. These values SHALL flow to the runtime MCP client so the operator can tune per-server timeouts without code changes.

#### Scenario: Agent-declared timeouts honored
- **WHEN** an agent's `mcp_servers` entry declares `connect_timeout` and `call_timeout`
- **THEN** the MCP server configuration registered for that agent carries those timeout values

#### Scenario: Omitted timeouts fall back to defaults
- **WHEN** an agent's `mcp_servers` entry omits the timeout fields
- **THEN** the registered MCP server configuration uses the default connect and call timeouts
