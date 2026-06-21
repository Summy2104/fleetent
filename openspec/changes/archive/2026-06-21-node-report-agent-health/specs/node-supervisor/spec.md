## ADDED Requirements

### Requirement: Node reports per-agent health

When the node supervisor reports actual state, it SHALL determine and include each running agent's `health` by probing the agent's loopback `/health` endpoint (using the agent's recorded gateway port): a `200` response maps to `healthy`, any non-200 / unreachable maps to `unhealthy`; an agent without a gateway port falls back to process liveness (`is_alive` → `healthy`). The probe SHALL be bulkheaded — a single agent's probe failure marks that agent `unhealthy` and MUST NOT affect other agents' reporting or kill the reconcile loop.

#### Scenario: Healthy agent reported healthy

- **WHEN** a running agent's loopback `/health` returns 200
- **THEN** the status report for that agent includes `health = "healthy"`, persisted to `node_agent_status.health`

#### Scenario: Unresponsive agent reported unhealthy

- **WHEN** a running agent's loopback `/health` is unreachable or returns non-200
- **THEN** the report includes `health = "unhealthy"`, and the reconcile loop and other agents' reporting are unaffected

#### Scenario: Probe failure is bulkheaded

- **WHEN** probing one agent raises or times out
- **THEN** that agent is reported `unhealthy`, the exception does not propagate, and the loop continues
