# agent-definition Delta

## MODIFIED Requirements

### Requirement: Agent hard deletion

The store SHALL expose `agent_store.delete_agent(name)` that removes the agent, all its versions, and its binding child rows in a single transaction (delete `agent_mcp_server_bindings` and `agent_oauth_bindings` rows, then `agent_versions` rows, then the `agents` row, in FK-safe order). It SHALL return a boolean: `True` when a row was deleted, `False` when no agent with that name exists. SQL SHALL use named parameters and go through the store boundary; no ORM.

#### Scenario: Delete removes agents and agent_versions rows

- **WHEN** `agent_store.delete_agent("assistant")` is called for an existing agent with N versions
- **THEN** the `agents` row and all N `agent_versions` rows are removed in one transaction AND the call returns `True`

#### Scenario: Delete cleans binding child rows

- **WHEN** `agent_store.delete_agent("assistant")` is called for an agent holding MCP server bindings and OAuth bindings
- **THEN** the `agent_mcp_server_bindings` and `agent_oauth_bindings` rows for that agent are removed in the same transaction（FK 强制下不报约束错误，且不留孤儿绑定行）

#### Scenario: Delete of unknown agent returns False

- **WHEN** `agent_store.delete_agent("nope")` is called and no such agent exists
- **THEN** no rows are modified AND the call returns `False`
