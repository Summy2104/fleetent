## ADDED Requirements

### Requirement: MCP server timeout fields documented in the official example

The `connect_timeout` and `call_timeout` fields of an MCP server definition SHALL be
shown in the official `agents/default/agent.yaml.example` with their default values and
a brief comment, so operators can discover and configure them.

#### Scenario: Example file shows connect_timeout

- **WHEN** an operator reads `agents/default/agent.yaml.example`
- **THEN** they find `connect_timeout` (default 10.0) in at least one `mcp_servers` entry

#### Scenario: Example file shows call_timeout

- **WHEN** an operator reads `agents/default/agent.yaml.example`
- **THEN** they find `call_timeout` (default 30.0) in at least one `mcp_servers` entry
