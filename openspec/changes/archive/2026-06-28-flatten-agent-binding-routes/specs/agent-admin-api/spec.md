## MODIFIED Requirements

### Requirement: Binding endpoints
The system SHALL expose endpoints to bind and unbind **users** to/from an agent, to bind and unbind **IM groups** (`platform` + `group_id`) for an agent, and to set the agent's **IM capability** flags (`supports_dm` / `supports_groups`), all requiring `admin`/`built_in_admin`. The user and group binding write routes SHALL be addressed per-type **without** a `/bindings/` prefix, matching the existing skill binding routes (`PUT /admin/agents/{name}/skills/{skill_name}`). （Channel-routing 绑定已于阶段 1 移除；群白名单是访问控制、非路由——见 im-access-model。运行时强制属阶段 3。）

#### Scenario: Bind user
- **WHEN** an admin sends `POST /admin/agents/{name}/users` with body `{"user_id":"u1"}`
- **THEN** a row is inserted into `user_agents` and the response is 201

#### Scenario: Unbind user
- **WHEN** an admin sends `DELETE /admin/agents/{name}/users/{user_id}`
- **THEN** the matching `user_agents` row is removed and the response is 204

#### Scenario: Bind IM group
- **WHEN** an admin sends `POST /admin/agents/{name}/groups` with body `{"platform":"slack","group_id":"C0123"}`
- **THEN** a row is inserted into `agent_im_groups` keyed `(agent_id, "slack", "C0123")` and the response is 201

#### Scenario: Unbind IM group
- **WHEN** an admin sends `DELETE /admin/agents/{name}/groups/{platform}/{group_id}`
- **THEN** the matching `agent_im_groups` row is removed and the response is 204

#### Scenario: Set IM capability
- **WHEN** an admin sets the agent's `supports_dm` / `supports_groups`
- **THEN** the corresponding `agents` columns are updated and the response is 200

#### Scenario: Bind to missing agent
- **WHEN** a binding/capability endpoint targets an agent name that does not exist
- **THEN** the response is 404

#### Scenario: Viewer cannot configure
- **WHEN** a `viewer` calls any user/group binding or capability write endpoint
- **THEN** the response is 403

### Requirement: Agent MCP binding endpoints
The agent admin API SHALL expose `POST /admin/agents/{name}/mcp/{server_id}`
and `DELETE /admin/agents/{name}/mcp/{server_id}` to bind and unbind an MCP
server for an agent (per-type, no `/bindings/` prefix). Writes SHALL require admin role and SHALL be audited. The POST
SHALL reject an unknown `server_id` (not present in `GET /admin/mcp/servers`) with 404.

#### Scenario: Bind a known MCP server

- **WHEN** an admin POSTs `/admin/agents/support-bot/mcp/github` and "github" is a known server
- **THEN** the binding is recorded and the action is audited

#### Scenario: Bind an unknown MCP server

- **WHEN** an admin POSTs `/admin/agents/support-bot/mcp/nope` and "nope" is not a known server
- **THEN** the endpoint responds 404 and no binding is recorded

#### Scenario: Viewer cannot bind

- **WHEN** a viewer attempts the POST or DELETE MCP binding route
- **THEN** the request is rejected as forbidden

## ADDED Requirements

### Requirement: Agent per-type binding read endpoints
The agent admin API SHALL expose one read endpoint per outbound/inbound binding type, each returning that single type's bound items for the agent, replacing the former aggregate read. It SHALL expose `GET /admin/agents/{name}/users` (bound user ids), `GET /admin/agents/{name}/groups` (bound IM groups as `platform` + `group_id`), and `GET /admin/agents/{name}/mcp` (bound MCP `server_id`s). These join the existing per-type reads `GET /admin/agents/{name}/skills`, `GET /admin/agents/{name}/kbs`, and `GET /admin/agents/{name}/secrets`. Reads SHALL be allowed for viewer and admin roles, and SHALL respond 404 for an unknown agent name.

#### Scenario: Read bound users
- **WHEN** an admin or viewer sends `GET /admin/agents/{name}/users`
- **THEN** the response lists the agent's bound user ids

#### Scenario: Read bound IM groups
- **WHEN** an admin or viewer sends `GET /admin/agents/{name}/groups`
- **THEN** the response lists the agent's bound IM groups as `platform` + `group_id`

#### Scenario: Read bound MCP servers
- **WHEN** an admin or viewer sends `GET /admin/agents/{name}/mcp`
- **THEN** the response lists the agent's bound MCP `server_id`s

#### Scenario: Unknown agent on per-type read
- **WHEN** any per-type read endpoint targets an agent name that does not exist
- **THEN** the response is 404

## REMOVED Requirements

### Requirement: Agent binding read endpoint
**Reason**: The aggregate `GET /admin/agents/{name}/bindings` was a false aggregate — it bundled `users` + `groups` + `mcp_servers` (omitting `kbs`/`skills`/`secrets`) and its sole consumer (the admin console) immediately split the payload across separate tabs. It is replaced by symmetric per-type read endpoints.

**Migration**: Callers SHALL replace `GET /admin/agents/{name}/bindings` with the per-type reads `GET /admin/agents/{name}/users`, `GET /admin/agents/{name}/groups`, and `GET /admin/agents/{name}/mcp` (defined in "Agent per-type binding read endpoints").
