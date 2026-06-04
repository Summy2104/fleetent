## ADDED Requirements

### Requirement: Agent knowledge-base binding endpoints
The agent admin API SHALL expose agent-side endpoints to manage an agent's knowledge-base bindings over the existing `agent_kbs` store, so the agent console can list and edit them without going through the KB module. Reads SHALL allow viewer or admin; writes SHALL require admin. The endpoints resolve the agent by name to its id and operate within the agent's tenant.

#### Scenario: List an agent's knowledge bases
- **WHEN** a viewer or admin calls `GET /admin/agents/{name}/kbs`
- **THEN** the response lists the kb_ids bound to that agent

#### Scenario: Bind a knowledge base to an agent
- **WHEN** an admin calls `POST /admin/agents/{name}/kbs` with a `kb_id`
- **THEN** the binding is created (idempotently) via the `agent_kbs` store and the kb_id appears in the agent's bound list

#### Scenario: Unbind a knowledge base from an agent
- **WHEN** an admin calls `DELETE /admin/agents/{name}/kbs/{kb_id}`
- **THEN** the binding is removed and the kb_id no longer appears in the agent's bound list

#### Scenario: Viewer cannot mutate KB bindings
- **WHEN** a viewer calls the bind or unbind endpoint
- **THEN** the request is rejected with 403

### Requirement: Agent OAuth connector binding endpoints
The agent admin API SHALL expose agent-side endpoints to manage which OAuth connectors an agent may use, parallel to the MCP binding endpoints. Reads SHALL allow viewer or admin; writes SHALL require admin. Binding a connector that does not exist in the connector catalog SHALL be rejected.

#### Scenario: List an agent's OAuth connector bindings
- **WHEN** a viewer or admin calls `GET /admin/agents/{name}/bindings/oauth`
- **THEN** the response lists the connector_ids bound to that agent

#### Scenario: Bind an OAuth connector to an agent
- **WHEN** an admin calls `POST /admin/agents/{name}/bindings/oauth/{connector_id}` for an existing connector
- **THEN** the binding is created (idempotently) and the connector_id appears in the agent's bound list

#### Scenario: Bind rejects unknown connector
- **WHEN** an admin binds a connector_id that is not in the connector catalog
- **THEN** the request is rejected with 404

#### Scenario: Unbind an OAuth connector from an agent
- **WHEN** an admin calls `DELETE /admin/agents/{name}/bindings/oauth/{connector_id}`
- **THEN** the binding is removed

#### Scenario: Viewer cannot mutate OAuth bindings
- **WHEN** a viewer calls the bind or unbind endpoint
- **THEN** the request is rejected with 403
