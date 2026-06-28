## MODIFIED Requirements

### Requirement: MCP servers managed natively in the React SPA

The React admin SPA SHALL render MCP servers natively (within the Connectors domain, not a deep-link to legacy) and SHALL support the full lifecycle against the existing admin API: list, create, edit, delete, test, reconnect, view tools, and run doctor. This closes the legacy create-only gap. **Create/edit 的鉴权部分 SHALL 按 `auth_type` 动态渲染**:选 `api_key` 显示单个 env-name 字段、选 `oauth_client_credentials` 显示 token_url / client_id / scope / client_secret-env-name 字段(字段集由 `mcp-auth-config` 的类型 schema 驱动)。表单 MUST NOT 暴露扁平 `api_key_env` 输入(改由结构化 `auth_config` 承载),且 MUST NOT 接受 secret 明文(只接受 env 引用名,值经 secret 接口存 `agent_secrets`)。**Create SHALL 允许选择 server scope** —— 全局默认(`agent_id` 为空)或某 owning agent(agent-private,经 create 请求传 `agent_id`),闭合"建窗只能建全局行"的实现缺口(owning agent 的展示/过滤见本 capability 既有要求)。

#### Scenario: Edit, delete, and test an MCP server from the SPA

- **WHEN** an admin edits an existing MCP server and saves, deletes one (with confirmation), or tests one from the React admin SPA
- **THEN** the SPA calls `PUT /admin/mcp/servers/{id}` / `DELETE /admin/mcp/servers/{id}` / `POST /admin/mcp/servers/{id}/test` and reflects the result

#### Scenario: View tools and reconnect in the SPA

- **WHEN** an admin lists an MCP server's tools or reconnects it from the React admin SPA
- **THEN** the SPA calls `GET /admin/mcp/servers/{id}/tools` and `POST /admin/mcp/servers/{id}/reconnect`, and shows the outcome

#### Scenario: 鉴权表单按 auth_type 动态渲染

- **WHEN** 管理员在 create/edit 表单切换 `auth_type`(api_key ↔ oauth_client_credentials)
- **THEN** 表单显示该类型对应的字段集(api_key:1 个 env 名;oauth:token_url/client_id/scope/client_secret-env),且只收 env 引用名、不收 secret 明文、不显示扁平 `api_key_env` 输入

#### Scenario: 建全局或 agent 私有 server

- **WHEN** 管理员在 create 选择 scope=全局(不选 agent)或 scope=某 agent
- **THEN** SPA 在 create 请求带 `agent_id`(全局为空 / 私有为该 agent id),注册表据此建全局默认行或 agent 私有行
