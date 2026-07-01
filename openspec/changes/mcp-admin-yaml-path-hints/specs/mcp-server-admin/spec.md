## ADDED Requirements

### Requirement: MCP server 表单字段展示对应的 agent.yaml 路径

React 管理 SPA 的 MCP server 新建/编辑表单 SHALL 在每个字段输入框下方常驻展示该字段最终落在 `agent.yaml` 的路径(如 `mcpServers.filesystem.x-fleetent.auth.client_id`),路径数据 SHALL 从后端 `GET /admin/mcp/field-schema` 获取,该端点返回的路径表 MUST 直接派生自 `config.py` 的 `MCP_FLEETENT_EXT_DEFAULTS` 整形规则(与 `materialize._mcp_payload_to_map` 的真实写盘行为保持一致),不得在前端另外手写一份独立的映射表。路径模板中的 `{id}` 占位符 SHALL 替换为表单当前 ID 输入框的实际值,未填写时回退显示 `<id>`。`id` 输入框本身(对应 `mcpServers` 的 map key)和"作用域"选择器(对应 `agent_id` 路由列,不进入某份 `agent.yaml` 内容)SHALL 展示单独手写的说明文案,不依赖 `field-schema` 返回值。

#### Scenario: 切换鉴权类型时提示随之更新

- **WHEN** 管理员在新建/编辑表单把鉴权类型从 `api_key` 切换到 `oauth_client_credentials`
- **THEN** 新出现的 Token URL / Client ID / Client secret 环境变量名等字段下方分别展示 `mcpServers.{id}.x-fleetent.auth.token_url`、`mcpServers.{id}.x-fleetent.auth.client_id`、`mcpServers.{id}.x-fleetent.auth.client_secret_env`,原 `api_key` 相关的提示(`mcpServers.{id}.api_key_env`)随字段一起消失

#### Scenario: 路径提示随 ID 输入实时更新

- **WHEN** 管理员在 ID 输入框填入 `filesystem`
- **THEN** 其余字段下方的提示把占位符替换为实际值,例如"传输方式"字段下方显示 `mcpServers.filesystem.transport`

#### Scenario: 未登录请求被拒绝

- **WHEN** 一个不带有效登录会话的请求访问 `GET /admin/mcp/field-schema`
- **THEN** 响应为 401
