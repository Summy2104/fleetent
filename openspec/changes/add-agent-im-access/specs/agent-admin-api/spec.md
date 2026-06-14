# agent-admin-api Delta

## MODIFIED Requirements

### Requirement: Binding endpoints
The system SHALL expose endpoints to bind and unbind **users** to/from an agent, to bind and unbind **IM groups** (`platform` + `group_id`) for an agent, and to set the agent's **IM capability** flags (`supports_dm` / `supports_groups`), all requiring `admin`/`built_in_admin`. （Channel-routing 绑定已于阶段 1 移除；群白名单是访问控制、非路由——见 im-access-model。运行时强制属阶段 3。）

#### Scenario: Bind user
- **WHEN** an admin sends `POST /admin/agents/{name}/bindings/users` with body `{"user_id":"u1"}`
- **THEN** a row is inserted into `user_agents` and the response is 201

#### Scenario: Unbind user
- **WHEN** an admin sends `DELETE /admin/agents/{name}/bindings/users/{user_id}`
- **THEN** the matching `user_agents` row is removed and the response is 204

#### Scenario: Bind IM group
- **WHEN** an admin sends `POST /admin/agents/{name}/bindings/groups` with body `{"platform":"slack","group_id":"C0123"}`
- **THEN** a row is inserted into `agent_im_groups` keyed `(agent_id, "slack", "C0123")` and the response is 201

#### Scenario: Unbind IM group
- **WHEN** an admin sends `DELETE /admin/agents/{name}/bindings/groups/{platform}/{group_id}`
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
