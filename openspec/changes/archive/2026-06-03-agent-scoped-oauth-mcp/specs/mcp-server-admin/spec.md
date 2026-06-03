## MODIFIED Requirements

### Requirement: MCP server list and connection status
The admin face SHALL list all configured MCP servers (stdio / HTTP transport) with a
connection status aligned to the `mcp` domain: connected, startup-degraded (masked at
startup), probe-failing-reconnecting (exponential backoff), and marked-permanently-
unavailable. Each entry SHALL show its owning agent (or "global default" for entries
sourced from `config/mcp.servers.yaml`), registered tool count, the `server__{tool}`
namespace list, and the last handshake/probe time. The list SHALL support filtering by
owning agent. Connection state is delegated to the `mcp` domain and SHALL NOT be
recomputed here.

#### Scenario: Startup-degraded server visible (场景 112)
- **WHEN** an admin opens the MCP server list while an HTTP MCP server was degraded after a failed startup handshake
- **THEN** that server shows "startup-degraded" with registered tool count 0, the rest of the platform is unaffected, and a "manual reconnect" action is available

#### Scenario: Connection states distinguished
- **WHEN** servers are respectively connected, reconnecting under backoff, and marked permanently unavailable
- **THEN** the list shows each distinct status as reported by the `mcp` domain

#### Scenario: Owning agent shown and filterable
- **WHEN** an admin filters the MCP server list by agent `billing`
- **THEN** only `billing`-owned servers and applicable global defaults are listed, each labeled with its owning agent or "global default"
