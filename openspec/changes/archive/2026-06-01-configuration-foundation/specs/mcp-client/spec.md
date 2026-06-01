## MODIFIED Requirements

### Requirement: Startup tool registration
The system SHALL connect to MCP servers configured in `config/settings.yaml` under `mcp.servers` at startup
and register their tools into `tool_registry`.

#### Scenario: MCP tools available at runtime
- **WHEN** the service starts with `config/settings.yaml` listing a GitHub MCP server with a `create_issue` tool
- **THEN** `tool_registry` contains a tool named `github__create_issue` before the first request is handled

#### Scenario: No MCP servers configured
- **WHEN** `mcp.servers` is empty
- **THEN** service startup continues normally and no MCP tools are registered

#### Scenario: MCP server unreachable at startup
- **WHEN** a configured MCP server is not reachable at startup
- **THEN** a warning is logged, that server's tools are skipped, and service startup continues normally
