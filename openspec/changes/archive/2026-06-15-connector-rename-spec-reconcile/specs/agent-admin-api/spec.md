# agent-admin-api Specification

## MODIFIED Requirements

### Requirement: Agent OAuth connector binding endpoints
The agent admin API SHALL expose agent-side endpoints to manage which external services an agent may use, parallel to the MCP binding endpoints. Reads SHALL allow viewer or admin; writes SHALL require admin. Binding a service that does not exist in the external services registry SHALL be rejected. HTTP 端点路径与路径参数 token 保持不变（`/admin/agents/{name}/bindings/oauth/{connector_id}`，向后兼容；token `connector_id` 语义即 `service_id`）。

#### Scenario: List an agent's external-service bindings
- **WHEN** a viewer or admin calls `GET /admin/agents/{name}/bindings/oauth`
- **THEN** the response lists the service ids bound to that agent

#### Scenario: Bind a service to an agent
- **WHEN** an admin calls `POST /admin/agents/{name}/bindings/oauth/{connector_id}` for an existing service
- **THEN** the binding is created (idempotently) and the service id appears in the agent's bound list

#### Scenario: Bind rejects unknown service
- **WHEN** an admin binds a service id that is not in the external services registry
- **THEN** the request is rejected with 404

#### Scenario: Unbind a service from an agent
- **WHEN** an admin calls `DELETE /admin/agents/{name}/bindings/oauth/{connector_id}`
- **THEN** the binding is removed

#### Scenario: Viewer cannot mutate bindings
- **WHEN** a viewer calls the bind or unbind endpoint
- **THEN** the request is rejected with 403
