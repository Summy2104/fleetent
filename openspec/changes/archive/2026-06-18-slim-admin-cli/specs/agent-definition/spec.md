## MODIFIED Requirements

### Requirement: User-to-agent assignment
The system SHALL support assigning one or more agents to a user via the `user_agents` table. The assignment SHALL be operated through the HTTP admin API (`POST` / `DELETE /admin/agents/{name}/bindings/users/{user_id}`); the legacy `fleetent-admin assign-user` / `unassign-user` CLI commands are removed.

#### Scenario: User assigned via HTTP
- **WHEN** admin calls `POST /admin/agents/{name}/bindings/users/{user_id}`
- **THEN** a row exists in `user_agents(user_id, agent_id)`

#### Scenario: User unassigned via HTTP
- **WHEN** admin calls `DELETE /admin/agents/{name}/bindings/users/{user_id}`
- **THEN** the matching row in `user_agents` is removed

#### Scenario: Look up user's agent resolves to active snapshot
- **WHEN** a message arrives from `user_id=X` who is bound to agent `agent_id=1`
- **THEN** the system retrieves the active `AgentSnapshot` for `agent_id=1` and applies its system_prompt, allowed_tools, skills_dir, mcp_server_ids, model_overrides, memory_namespace
