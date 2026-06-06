## MODIFIED Requirements

### Requirement: Startup tool registration

The system SHALL register MCP tools from Platform-authored MCP server definitions, not from
`config/mcp.servers.yaml`. Global-default definitions are stored in Platform DB with no agent scope;
agent-owned definitions are stored with an agent scope and override a global-default definition with
the same `server_id` for that agent. Materialized Agent homes SHALL carry the Agent's effective MCP
server definitions in `agent.yaml`.

#### Scenario: Global DB-authored MCP tools available at runtime
- **WHEN** Platform DB contains an enabled global-default GitHub MCP server with a `create_issue` tool
- **THEN** startup registers a tool named `github__create_issue` before the first request is handled

#### Scenario: No MCP servers configured
- **WHEN** Platform DB contains no enabled global-default MCP servers
- **THEN** service startup continues normally and no global-default MCP tools are registered

#### Scenario: Config file is not read
- **WHEN** `config/mcp.servers.yaml` exists in the working tree or Platform home
- **THEN** startup ignores it
- **AND** MCP registration is derived from Platform DB / materialized Agent config only

#### Scenario: Agent-owned server overrides global default
- **WHEN** a global-default `github` server is registered at startup AND agent `billing`
  owns its own `github` server definition
- **THEN** resolving MCP servers for agent `billing` uses the `billing`-owned `github`
  definition rather than the global-default one

### Requirement: Dedicated MCP server definition file

MCP server definitions SHALL NOT live in `config/mcp.servers.yaml` or any other default config file.
They SHALL be authored through Platform DB and materialized into Agent `agent.yaml` when needed by
an Agent runtime.

#### Scenario: Repository has no MCP server config template
- **WHEN** 查看配置样例
- **THEN** `config/mcp.servers.yaml.example` 不存在
- **AND** `config/` 不存在

#### Scenario: Legacy MCP config path is ignored
- **WHEN** `config/mcp.yaml` or `config/mcp.servers.yaml` exists
- **THEN** startup does not load either file as current configuration
