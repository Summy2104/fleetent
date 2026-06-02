# mcp-client Specification

## Purpose
Defines MCP server startup registration and transparent MCP tool dispatch.
## Requirements
### Requirement: Startup tool registration
The system SHALL connect to MCP servers configured in `config/mcp.servers.yaml` at startup and register
their tools into `tool_registry`. MCP global policy SHALL remain in `config/settings.yaml` under `mcp`.

#### Scenario: MCP tools available at runtime
- **WHEN** the service starts with `config/mcp.servers.yaml` listing a GitHub MCP server with a
  `create_issue` tool
- **THEN** `tool_registry` contains a tool named `github__create_issue` before the first request is handled

#### Scenario: No MCP servers configured
- **WHEN** `config/mcp.servers.yaml` does not exist or contains no servers
- **THEN** service startup continues normally and no MCP tools are registered

#### Scenario: MCP disabled globally
- **WHEN** `config/settings.yaml` sets `mcp.enabled=false`
- **THEN** service startup does not read or register MCP servers from `config/mcp.servers.yaml`

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
- **THEN** `tool_registry.dispatch` routes it to `fleetent.integrations.mcp.call_tool("github", "create_issue", args, user_id)` transparently

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

### Requirement: Dedicated MCP server definition file
MCP server definitions SHALL live in `config/mcp.servers.yaml`, not in `config/settings.yaml`.

#### Scenario: Settings file excludes MCP server definitions
- **WHEN** `config/settings.yaml` contains `mcp.servers`
- **THEN** startup rejects the configuration rather than silently treating it as the server registry

#### Scenario: Example file documents dedicated format
- **WHEN** 查看配置样例
- **THEN** `config/mcp.servers.yaml.example` documents the server list format and
  `config/settings.yaml.example` does not include server list examples

#### Scenario: Legacy MCP config path remains rejected
- **WHEN** `config/mcp.yaml` exists
- **THEN** startup fails fast and points operators to `config/mcp.servers.yaml`
