# agent-admin-api Delta

## MODIFIED Requirements

### Requirement: Binding endpoints
The system SHALL expose endpoints to bind and unbind **users** to/from an agent, requiring `admin`. （Channel 绑定端点随 `channel_agents` descope 移除——一 agent 一 bot 模型下消息由连接器连接定 agent，无需按渠道绑定。）

#### Scenario: Bind user
- **WHEN** an admin sends `POST /admin/agents/{name}/bindings/users` with body `{"user_id":"u1"}`
- **THEN** a row is inserted into `user_agents` and the response is 201

#### Scenario: Unbind user
- **WHEN** an admin sends `DELETE /admin/agents/{name}/bindings/users/{user_id}`
- **THEN** the matching `user_agents` row is removed and the response is 204

#### Scenario: Bind to missing agent
- **WHEN** a binding endpoint targets an agent name that does not exist
- **THEN** the response is 404

#### Scenario: Channel binding endpoints removed
- **WHEN** a request hits `POST` or `DELETE /admin/agents/{name}/bindings/channels*`
- **THEN** the route does not exist (404) — channel-to-agent binding has been descoped
