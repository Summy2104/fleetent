## MODIFIED Requirements

### Requirement: Per-agent MCP server allowlist
An `AgentSnapshot.mcp_server_ids` SHALL constrain which MCP server tools are visible to
the agent. MCP tools whose `{server_id}__` prefix is not in the list SHALL be filtered
out of the tool schema for that request. Beyond visibility, MCP server *definitions* and
*credentials* SHALL be resolved within the agent scope: the same `server_id` MAY map to a
different definition and credential per agent, and a tool dispatch SHALL use the session
and credential belonging to the dispatching agent's resolved server, never a shared
global session for that `server_id`.

#### Scenario: Tool from allowed server visible
- **WHEN** `mcp_server_ids = ["github"]` and the request happens to invoke `github__create_issue`
- **THEN** the tool schema offered to the LLM contains `github__create_issue`

#### Scenario: Tool from non-allowed server hidden
- **WHEN** `mcp_server_ids = ["github"]` and `gitlab__create_issue` is also registered
- **THEN** the tool schema offered to the LLM does NOT contain `gitlab__create_issue`

#### Scenario: Empty list hides all MCP tools
- **WHEN** `mcp_server_ids = []`
- **THEN** no MCP server tool appears in the schema; built-in tools are unaffected

#### Scenario: Same server id isolated across agents
- **WHEN** agent `billing` and agent `sales` both allow and resolve `github` with
  different credentials
- **THEN** a `github` tool dispatch under `billing` uses `billing`'s credential/session
  and a dispatch under `sales` uses `sales`'s, with no shared session
