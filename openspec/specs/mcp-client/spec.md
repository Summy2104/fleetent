## ADDED Requirements

### Requirement: Startup tool registration
The system SHALL connect to all configured MCP servers at startup and register their tools into `tool_registry`.

#### Scenario: MCP tools available at runtime
- **WHEN** the service starts with `config/mcp.yaml` listing a GitHub MCP server with a `create_issue` tool
- **THEN** `tool_registry` contains a tool named `github__create_issue` before the first request is handled

#### Scenario: MCP server unreachable at startup
- **WHEN** a configured MCP server is not reachable at startup
- **THEN** a warning is logged, that server's tools are skipped, and service startup continues normally

### Requirement: Tool naming convention
MCP tools SHALL be registered with the prefix `{server_id}__{tool_name}` (double underscore).

#### Scenario: Tool name derivation
- **WHEN** MCP server `linear` exposes a tool `create_ticket`
- **THEN** it is registered as `linear__create_ticket` in `tool_registry`

#### Scenario: No naming collision with local tools
- **WHEN** a local tool and an MCP tool have the same base name
- **THEN** the MCP tool's double-underscore prefix prevents collision (e.g., local `shell` vs `my_server__shell`)

### Requirement: Transparent tool dispatch
The agent_loop and LLM SHALL be unaware of whether a tool is local or from an MCP server.

#### Scenario: LLM tool call routing
- **WHEN** LLM calls `github__create_issue` in its tool_use block
- **THEN** `tool_registry.dispatch` routes it to `mcp_client.call_tool("github", "create_issue", args, user_id)` transparently

### Requirement: Module interface
The mcp_client module SHALL expose `register_all` and `call_tool` as its primary interface.

#### Scenario: register_all called at startup
- **WHEN** service starts
- **THEN** `mcp_client.register_all(servers: list[McpServerConfig])` is called once, registering all tools

#### Scenario: call_tool invoked per dispatch
- **WHEN** a MCP tool is dispatched
- **THEN** `mcp_client.call_tool(server_id, tool_name, args, user_id)` forwards the call to the appropriate MCP server
