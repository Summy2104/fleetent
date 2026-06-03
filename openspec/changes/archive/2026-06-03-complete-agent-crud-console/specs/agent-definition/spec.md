## ADDED Requirements

### Requirement: Agent hard deletion

The store SHALL expose `agent_store.delete_agent(name)` that removes the agent and all its versions in a single transaction (delete `agent_versions` rows then the `agents` row, in FK-safe order). It SHALL return a boolean: `True` when a row was deleted, `False` when no agent with that name exists. SQL SHALL use named parameters and go through the store boundary; no ORM.

#### Scenario: Delete removes agents and agent_versions rows

- **WHEN** `agent_store.delete_agent("assistant")` is called for an existing agent with N versions
- **THEN** the `agents` row and all N `agent_versions` rows are removed in one transaction AND the call returns `True`

#### Scenario: Delete of unknown agent returns False

- **WHEN** `agent_store.delete_agent("nope")` is called and no such agent exists
- **THEN** no rows are modified AND the call returns `False`
