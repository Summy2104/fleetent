# mcp-client Specification

## Purpose
Defines MCP server startup registration and transparent MCP tool dispatch.
## Requirements
### Requirement: Startup tool registration

The system SHALL register MCP tools from Platform-authored MCP server definitions, not from
legacy MCP YAML files. Global-default definitions are stored in Platform DB with no agent scope;
agent-owned definitions are stored with an agent scope and override a global-default definition
with the same `server_id` for that agent. Materialized Agent homes SHALL carry the Agent's
effective MCP server definitions in `agent.yaml` using the standard `mcpServers` map format.

#### Scenario: Global DB-authored MCP tools available at runtime
- **WHEN** Platform DB contains an enabled global-default GitHub MCP server with a `create_issue` tool
- **THEN** startup registers that tool, exposed to the LLM as `mcp__github__create_issue` under the default projection, before the first request is handled

#### Scenario: No MCP servers configured
- **WHEN** Platform DB contains no enabled global-default MCP servers
- **THEN** service startup continues normally and no global-default MCP tools are registered

#### Scenario: Config file is not read
- **WHEN** a legacy MCP YAML file exists in the working tree or Platform home
- **THEN** startup ignores it
- **AND** MCP registration is derived from Platform DB / materialized Agent config only

#### Scenario: Agent-owned server overrides global default
- **WHEN** a global-default `github` server is registered at startup AND agent `billing`
  owns its own `github` server definition
- **THEN** resolving MCP servers for agent `billing` uses the `billing`-owned `github`
  definition rather than the global-default one

### Requirement: Tool naming convention
MCP tools SHALL be registered under a canonical identity and exposed to the LLM under a configurable projected name (see capability `mcp-tool-name-projection`). The default projection SHALL be `mcp__{server_id}__{tool_name}` (`mcp.tool_naming: claude`). Governance and dispatch SHALL operate on the canonical `(server_id, tool_name)` identity, independent of the projected name.

#### Scenario: Default tool name derivation
- **WHEN** MCP server `linear` exposes a tool `create_ticket` AND `mcp.tool_naming` is unset (default)
- **THEN** it is exposed to the LLM as `mcp__linear__create_ticket`

#### Scenario: No naming collision with local tools
- **WHEN** a local tool and an MCP tool have the same base name
- **THEN** the `mcp__`-prefixed projected name prevents collision (e.g., local `shell` vs `mcp__my_server__shell`)

### Requirement: Transparent tool dispatch
The agent_loop and LLM SHALL be unaware of whether a tool is local or from an MCP server.
An inbound tool call referencing a projected MCP tool name SHALL be resolved to its canonical
`(server_id, tool_name)` before dispatch. MCP dispatch SHALL resolve the server and credential
within the dispatching agent's scope and SHALL key its session by `(agent scope, server_id)`.

#### Scenario: LLM tool call routing
- **WHEN** the LLM calls the projected name `mcp__github__create_issue` (default projection) in its tool_use block
- **THEN** `tool_registry.dispatch` resolves it to server `github`, tool `create_issue` and routes to the MCP client transparently, using the dispatching agent's resolved `github` server and credential

#### Scenario: Session keyed by agent and server
- **WHEN** agent `billing` and agent `sales` each dispatch a `github` MCP tool
- **THEN** the MCP client uses a separate session keyed by `(billing, github)` and
  `(sales, github)` respectively, never a single shared `github` session

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

MCP server definitions SHALL NOT live in default YAML config files.
They SHALL be authored through Platform DB and materialized into Agent `agent.yaml` when needed by
an Agent runtime.

#### Scenario: Repository has no MCP server config template
- **WHEN** 查看配置样例
- **THEN** repository templates include no dedicated MCP server YAML example
- **AND** only the canonical Platform and Agent examples are shipped

#### Scenario: Legacy MCP config path is ignored
- **WHEN** a legacy MCP YAML file exists
- **THEN** startup does not load either file as current configuration

### Requirement: Standard MCP server configuration format
Agent MCP server definitions in `agent.yaml` SHALL use the de-facto-standard map-keyed form under a top-level `mcpServers` (or `mcp_servers`) key, where each entry is keyed by the server name (the `server_id`) and uses standard fields: `command`/`args`/`env` for stdio servers and `url`/`headers`/`type` for remote servers. When `type` is omitted, transport SHALL be auto-detected (presence of `command` → stdio; presence of `url` → remote). String values SHALL support `${VAR}` environment references. fleetent-specific settings (`degrade_mode`, `file_root`, `file_isolation`, self-hosted `auth`, `approval_rules`) SHALL be carried under a nested `x-fleetent` extension block on each entry, which standard MCP tooling ignores. The legacy `list-of-id` form SHALL NOT be parsed.

#### Scenario: standard stdio block is accepted
- **WHEN** `agent.yaml` contains `mcpServers: { filesystem: { command: "npx", args: [...], env: {...} } }`
- **THEN** the `filesystem` MCP server is registered with `server_id = filesystem` and stdio transport

#### Scenario: remote transport auto-detected
- **WHEN** an entry has `url` but no `type`
- **THEN** it is treated as a remote (streamable HTTP) server

#### Scenario: fleetent extensions under x-fleetent
- **WHEN** an entry carries `x-fleetent: { degrade_mode: strict, approval_rules: [...] }`
- **THEN** those settings apply to that server
- **AND** the standard core fields remain a valid, pasteable MCP block

#### Scenario: legacy list form rejected
- **WHEN** `agent.yaml` contains the legacy `mcp_servers: [ { id: ... } ]` list form
- **THEN** parsing does not accept it as MCP server definitions

