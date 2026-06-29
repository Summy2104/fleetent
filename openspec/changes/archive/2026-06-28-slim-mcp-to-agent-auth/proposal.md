## Why

平台 `mcp_servers` 用**扁平鉴权列**(`auth_type` / `api_key_env` / `headers`)表达 MCP 静态鉴权,只够 API Key 型:OAuth `client_credentials` 在 **managed 模式没有配置入口**(表无 OAuth 结构列,materialize 的 `auth` 块恒为 `None`),且每加一种鉴权方式就要加一列,不可扩展。本 change 把扁平鉴权列重构为 **`auth_type` + 结构化 `auth_config`**(可扩展的鉴权类型),补齐 managed 的 OAuth 静态鉴权入口。

核心约束(已在 explore 校准):
- **静态鉴权** = 平台配置 + secret 走 `agent_secrets`(唯一信源)+ node 中转明文 + agent 用 env;用户**接受**这个现状,不要 secret 脱离平台。
- **动态鉴权**(per-user authorization_code)**已 100% agent 自管实现**(`integrations/mcp/` 的 oauth_authcode / per_user_tokens / authorization),平台零参与——本 change **不碰**。
- secret **值**永不进 `mcp_servers` 表;`auth_config` 只存 secret 的 **env 引用名**,值在 `agent_secrets` 密文。

## What Changes

- **`mcp_servers` 鉴权列重构(BREAKING schema)**:保留 `auth_type`(discriminator)+ 新增 `auth_config`(JSON,装该类型的非密字段 + secret 的 env 引用名);**删** `api_key_env` 扁平列(折叠进 `auth_config.key_env`)。`headers` 保留为**连接级**字段(通用 http 头,非鉴权专属)。
- **鉴权类型 = discriminated union**:`auth_type` 选 `none` / `api_key` / `oauth_client_credentials`(可扩展第 N 种);每种类型一个 schema 声明字段并标注哪些是 secret env 引用。复用 `config.py` 既有的 `McpOAuthSettings`。
- **materialize 翻译**:`(auth_type, auth_config)` → agent.yaml 的现有鉴权字段(`McpServerSettings.auth_type` / `api_key_env` / `auth` 块);**agent 侧 schema 与 MCP client 消费不变**。
- **补 OAuth managed 入口**:managed 模式现在能配 `oauth_client_credentials` 静态鉴权(此前无入口)。
- **前端**:create/edit MCP 表单**按 `auth_type` 动态渲染**对应字段(api_key 显示 1 个 env;oauth 显示 token_url/client_id/scope/client_secret_env);list 标注 owning agent(全局/私有,闭合既有 spec 缺口)。
- **迁移 109**:现有 `api_key` 行的 `api_key_env` 折叠进 `auth_config`,drop `api_key_env` 列。
- **不碰**:动态鉴权(per-user)、`agent_secrets` 机制、MCP 运行时状态/reconnect/doctor、model/provider。

## Capabilities

### New Capabilities
- `mcp-auth-config`: 平台 MCP 静态鉴权的**结构化、可扩展配置**契约——`auth_type` + `auth_config`、鉴权类型 registry(discriminated union)、secret 走 env 引用 + `agent_secrets`、materialize 翻译为 agent.yaml 鉴权字段、managed 支持 api_key + oauth_client_credentials 且加新类型不改表。

### Modified Capabilities
- `mcp-server-admin`: create/edit MCP server 表单**按 `auth_type` 动态渲染**鉴权字段;不再暴露扁平 `api_key_env` 输入(改由 auth_config 结构承载)。`mcp-oauth2-auth` / `mcp-client` **不改**(本 change 向其对齐:agent.yaml 仍是 MCP 鉴权的最终形态)。

## Impact

- **Owning package**:`platform/connector_management/`(`mcp_server_store.py` 改鉴权列)+ `platform/agent_lifecycle/materialize.py`(仅 `_mcp_servers_for_agent`,**不碰** `_models_from_overrides`/`_target_from_model_override`)+ 鉴权类型 schema(新建平台侧 auth-config models 或复用 `config.py` 的 `McpOAuthSettings`)。Touches:`connector_admin_api.py`(MCP 端点的鉴权入参)、`frontend/src/features/mcp/`(动态表单)。
- **Owned tables**:`mcp_servers` 改鉴权列(迁移 109:新增 `auth_config`、drop `api_key_env`、保留 `auth_type`/`headers`)。
- **Public API**:MCP create/edit 端点鉴权入参从扁平 `api_key_env` 改为结构化 `auth_config`(按 auth_type)。
- **Config namespace**:agent.yaml `mcp_servers[].auth` / `api_key_env` 仍是 MCP 鉴权最终形态(已 spec,无新增);平台侧新增 `auth_config` 中间表示。
- **Cross-module deps**:`agent_secrets` 唯一信源链路复用(MCP secret 不另起存储);agent 侧 `integrations/mcp/client.py` 与动态鉴权**不动**。
- **验证基线**:managed 下 api_key 型 MCP 不回归(`auth_type` 不删、收进结构);OAuth client_credentials 型 managed 现在可配;agent `fleetent agent run` 不受影响(agent 侧消费 agent.yaml 现有字段)。
- **明确不碰**:动态 per-user 鉴权(已 agent 自管)、MCP 运行时状态/reconnect/doctor(跨解耦边界,独立 change)、model/provider(方向二)、secret 架构(平台仍是信源,用户已确认接受)。
