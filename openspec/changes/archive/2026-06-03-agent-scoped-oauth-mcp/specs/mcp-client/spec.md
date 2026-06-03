## MODIFIED Requirements

### Requirement: Startup tool registration
The system SHALL connect to MCP servers configured in `config/mcp.servers.yaml` at
startup and register their tools into `tool_registry` as the global-default layer. MCP
global policy SHALL remain in `config/settings.yaml` under `mcp`. In addition,
agent-owned MCP server definitions SHALL be resolvable per request; an agent-owned
definition for a given `server_id` SHALL override the global-default definition for that
agent.

#### Scenario: MCP tools available at runtime
- **WHEN** the service starts with `config/mcp.servers.yaml` listing a GitHub MCP server with a
  `create_issue` tool
- **THEN** `tool_registry` contains a tool named `github__create_issue` before the first request is handled

#### Scenario: No MCP servers configured
- **WHEN** `config/mcp.servers.yaml` does not exist or contains no servers
- **THEN** service startup continues normally and no global-default MCP tools are registered

#### Scenario: MCP disabled globally
- **WHEN** `config/settings.yaml` sets `mcp.enabled=false`
- **THEN** service startup does not read or register MCP servers from `config/mcp.servers.yaml`

#### Scenario: MCP server unreachable at startup
- **WHEN** a configured MCP server is not reachable at startup
- **THEN** a warning is logged, that server's tools are skipped, and service startup continues normally

#### Scenario: Agent-owned server overrides global default
- **WHEN** a global-default `github` server is registered at startup AND agent `billing`
  owns its own `github` server definition
- **THEN** resolving MCP servers for agent `billing` uses the `billing`-owned `github`
  definition rather than the global-default one

### Requirement: Transparent tool dispatch
The agent_loop and LLM SHALL be unaware of whether a tool is local or from an MCP server.
MCP dispatch SHALL resolve the server and credential within the dispatching agent's scope
and SHALL key its session by `(agent scope, server_id)`.

#### Scenario: LLM tool call routing
- **WHEN** LLM calls `github__create_issue` in its tool_use block
- **THEN** `tool_registry.dispatch` routes it to the MCP client transparently, using the
  dispatching agent's resolved `github` server and credential

#### Scenario: Session keyed by agent and server
- **WHEN** agent `billing` and agent `sales` each dispatch a `github` MCP tool
- **THEN** the MCP client uses a separate session keyed by `(billing, github)` and
  `(sales, github)` respectively, never a single shared `github` session
