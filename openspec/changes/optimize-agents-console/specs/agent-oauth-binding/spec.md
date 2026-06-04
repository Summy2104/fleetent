## ADDED Requirements

### Requirement: Per-agent OAuth connector binding store
The system SHALL persist which OAuth connectors an agent may use in a dedicated binding table, parallel to the MCP server binding table. The store SHALL expose `bind(agent_id, connector_id, created_by=None)`, `unbind(agent_id, connector_id)`, `list_connectors_for_agent(agent_id) -> list[str]`, and `list_agents_for_connector(connector_id) -> list[str]`. Binding SHALL be idempotent on `(agent_id, connector_id)`. SQL SHALL use named parameters and go through the store boundary; schema SHALL be created by an Alembic migration; no ORM.

#### Scenario: Bind then list is idempotent
- **WHEN** `bind(5, "github")` is called twice
- **THEN** `list_connectors_for_agent(5)` returns `["github"]` exactly once

#### Scenario: Unbind removes the binding
- **WHEN** a connector is bound to an agent and then `unbind(agent_id, connector_id)` is called
- **THEN** `list_connectors_for_agent(agent_id)` no longer contains that connector_id

#### Scenario: Binding is scoped per agent
- **WHEN** `bind(5, "github")` and `bind(7, "github")` are called
- **THEN** `list_agents_for_connector("github")` returns both agent ids and each agent lists `github`

#### Scenario: Migration creates the table
- **WHEN** Alembic upgrades to head on a fresh database
- **THEN** the agent OAuth binding table exists with columns for agent_id, connector_id, created_at, and created_by
