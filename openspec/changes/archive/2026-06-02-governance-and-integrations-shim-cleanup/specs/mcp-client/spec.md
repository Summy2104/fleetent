## MODIFIED Requirements

### Requirement: Module interface
The MCP integration module SHALL expose `register_all` and `call_tool` through
`fleetent.integrations.mcp` as its primary interface.

#### Scenario: register_all called at startup
- **WHEN** service starts
- **THEN** `fleetent.integrations.mcp.register_all(servers: list[McpServerConfig])` is called once,
  registering all tools

#### Scenario: call_tool invoked per dispatch
- **WHEN** a MCP tool is dispatched
- **THEN** `fleetent.integrations.mcp.call_tool(server_id, tool_name, args, user_id)` forwards the call to
  the appropriate MCP server
