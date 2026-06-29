## MODIFIED Requirements

### Requirement: 鉴权类型是可扩展的 discriminated union
`auth_type` SHALL 支持至少 `none` / `api_key` / `oauth_client_credentials` / `oauth_authorization_code` / `api_key_per_user`,并 SHALL 可新增鉴权类型而**无需改 `mcp_servers` 表结构**。每种类型 SHALL 由一个 schema(pydantic discriminated union,`auth_type` 为 discriminator)声明其字段集,并标注哪些字段是 secret 的 env 引用。该 schema SHALL 是 validation、materialize 翻译、前端表单渲染三处共用的单一真相源,且 SHALL 位于 agent 与 platform **都能 import 的中立模块**——agent 侧消费该 schema MUST NOT import `platform.*`(`platform/connector_management/mcp_auth.py` 留 re-export shim 以不破坏既有 import)。`oauth_authorization_code` 类型 SHALL 声明 `authorization_endpoint` / `token_url` / `client_id` / `scope` / `redirect_path` 非密字段与 `client_secret_env` secret env 引用,其 `client_id` SHALL 支持 `${ENV}` 引用解析。`api_key_per_user` 类型(per-user 动态 api-key/bearer)SHALL 声明非密字段 `header_style`(`bearer` 默认 / `x_api_key`,决定注入 `Authorization: Bearer` 还是 `X-API-Key`)与 `credential_input`(`form` 默认 / `tool` / `both`,决定允许的提交方式),且 MUST NOT 声明任何静态 key 的 env 引用(key 由用户运行时按三元组提供,不来自 env)——以此区别于静态 `api_key`(`key_env`)。复用 `config.py` 既有的 `McpOAuthSettings` 作为 oauth 类型的基础。

#### Scenario: 加新鉴权类型不改表
- **WHEN** 未来新增一种鉴权类型(如某自托管签名方案)
- **THEN** 仅新增一个类型 schema + 前端表单分支即可;`mcp_servers` 表结构(`auth_type` + `auth_config`)不变

#### Scenario: 非法 auth_config 被 validation 拒绝
- **WHEN** 提交的 `auth_config` 缺该 `auth_type` 必需字段(如 oauth 缺 token_url)
- **THEN** 经类型 schema validation 拒绝,不写入注册表

#### Scenario: authorization_code 型以结构化存储
- **WHEN** 管理员配置 `auth_type=oauth_authorization_code`,填 authorization_endpoint/token_url/client_id/scope/redirect_path 与 client_secret 的 env 名 `ACME_CS`
- **THEN** 注册表存 `auth_config={"authorization_endpoint":…,"token_url":…,"client_id":…,"scope":…,"redirect_path":…,"client_secret_env":"ACME_CS"}`,client_secret 值不入表

#### Scenario: agent 侧 import schema 不引入 platform 依赖
- **WHEN** agent runtime(`integrations/mcp`)消费鉴权 schema 做 validation/解析
- **THEN** 该 schema 从中立模块 import,模块边界守护确认未 import 任何 `platform.*`

#### Scenario: client_id 支持 env 引用解析
- **WHEN** 某 oauth 型 server 的 `client_id` 配为 `${ACME_CLIENT_ID}`
- **THEN** 运行时经 `_resolve_env_ref` 解析为环境变量 `ACME_CLIENT_ID` 的值,字面非 env 引用的 client_id 原样使用

#### Scenario: api_key_per_user 型以结构化存储且无静态 key 引用
- **WHEN** 管理员配置 `auth_type=api_key_per_user`,设 `header_style=bearer`、不设 `credential_input`
- **THEN** 注册表存 `auth_config={"header_style":"bearer","credential_input":"form"}`(默认 form),且不含任何静态 key 或 `key_env`——key 由用户运行时按三元组提供

#### Scenario: api_key_per_user 默认安全表单提交
- **WHEN** 一个 `api_key_per_user` server 未显式配 `credential_input`
- **THEN** validation 后 `credential_input` 默认为 `form`(仅安全表单,工具提交不可用)

### Requirement: materialize 把 auth_type + auth_config 翻译为 agent.yaml 鉴权字段
materialize SHALL 把注册表的 `(auth_type, auth_config)` 翻译为 agent.yaml 的现有鉴权表示(`McpServerSettings.auth_type` / `api_key_env`,以及 oauth 的 `auth` 块);agent 侧 `McpServerSettings` schema 与 `integrations/mcp/client.py` 的消费 MUST NOT 因此改变。`oauth_authorization_code` 型 SHALL 翻译为 agent.yaml 的 authorization_code `auth` 块(authorization_endpoint/token_url/client_id/scope/redirect_path/client_secret_env),使 agent 侧按 per-user OAuth 路径发起授权。`api_key_per_user` 型 SHALL 翻译为 agent.yaml 的 per-user api-key 鉴权表示(含 `header_style` 与 `credential_input`),使 agent 侧按 per-user 凭据路径触发提交并 per-request 注入。

#### Scenario: api_key 翻译进 agent.yaml
- **WHEN** materialize 一个 `auth_type=api_key`、`auth_config={"key_env":"MY_TOKEN"}` 的 server
- **THEN** 渲染的 agent.yaml 含 `auth_type: api_key` + `api_key_env: MY_TOKEN`,agent 侧 MCP client 照常发 `Authorization: Bearer`

#### Scenario: oauth 翻译进 agent.yaml auth 块
- **WHEN** materialize 一个 oauth_client_credentials server
- **THEN** 渲染的 agent.yaml 含 `auth` 块(grant=client_credentials + token_url/client_id/scope/client_secret_env),agent 侧按既有 OAuth 路径连接

#### Scenario: authorization_code 翻译进 agent.yaml auth 块
- **WHEN** materialize 一个 oauth_authorization_code server
- **THEN** 渲染的 agent.yaml 含 authorization_code `auth` 块(authorization_endpoint/token_url/client_id/scope/redirect_path/client_secret_env),agent 侧按 per-user OAuth authorization_code 路径发起授权

#### Scenario: api_key_per_user 翻译进 agent.yaml
- **WHEN** materialize 一个 `auth_type=api_key_per_user`、`auth_config={"header_style":"x_api_key","credential_input":"both"}` 的 server
- **THEN** 渲染的 agent.yaml 含 per-user api-key 鉴权表示(header_style=x_api_key、credential_input=both),agent 侧按 per-user 凭据路径触发提交并以 `X-API-Key` 注入
