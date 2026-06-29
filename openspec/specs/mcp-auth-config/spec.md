# mcp-auth-config Specification

## Purpose
TBD - created by archiving change slim-mcp-to-agent-auth. Update Purpose after archive.
## Requirements
### Requirement: MCP 静态鉴权用 auth_type + 结构化 auth_config
平台 `mcp_servers` 注册表的静态鉴权 SHALL 由 `auth_type`(discriminator)+ `auth_config`(结构化,持久为 JSON)表达,取代既有扁平鉴权列。`auth_config` SHALL 仅装该鉴权类型的**非密字段**(如 OAuth 的 token_url/client_id/scope)与 secret 的 **env 引用名**(如 `key_env` / `client_secret_env`)。secret 的**值** MUST NOT 出现在 `mcp_servers` 表或 `auth_config` 中。`headers` 保留为**连接级**字段(通用 http 头),不并入鉴权配置。SQL MUST 用 named parameters 经 store 边界,schema MUST 由迁移建立,无 ORM。

#### Scenario: api_key 鉴权以结构化存储
- **WHEN** 管理员为某 MCP server 配置 `auth_type=api_key`、引用 env `MY_TOKEN`
- **THEN** 注册表存 `auth_type=api_key` + `auth_config={"key_env": "MY_TOKEN"}`,表内无 secret 明文,`api_key_env` 扁平列不再存在

#### Scenario: oauth 鉴权以结构化存储
- **WHEN** 管理员配置 `auth_type=oauth_client_credentials`,填 token_url/client_id/scope 与 client_secret 的 env 名 `ACME_CS`
- **THEN** 注册表存 `auth_config={"token_url":…,"client_id":…,"scope":…,"client_secret_env":"ACME_CS"}`,client_secret 值不入表

### Requirement: 鉴权类型是可扩展的 discriminated union
`auth_type` SHALL 支持至少 `none` / `api_key` / `oauth_client_credentials` / `oauth_authorization_code`,并 SHALL 可新增鉴权类型而**无需改 `mcp_servers` 表结构**。每种类型 SHALL 由一个 schema(pydantic discriminated union,`auth_type` 为 discriminator)声明其字段集,并标注哪些字段是 secret 的 env 引用。该 schema SHALL 是 validation、materialize 翻译、前端表单渲染三处共用的单一真相源,且 SHALL 位于 agent 与 platform **都能 import 的中立模块**——agent 侧消费该 schema MUST NOT import `platform.*`(`platform/connector_management/mcp_auth.py` 留 re-export shim 以不破坏既有 import)。`oauth_authorization_code` 类型 SHALL 声明 `authorization_endpoint` / `token_url` / `client_id` / `scope` / `redirect_path` 非密字段与 `client_secret_env` secret env 引用,其 `client_id` SHALL 支持 `${ENV}` 引用解析。复用 `config.py` 既有的 `McpOAuthSettings` 作为 oauth 类型的基础。

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

### Requirement: MCP 鉴权 secret 经 agent_secrets 唯一信源,平台不持明文
`auth_config` 中的 secret 字段 SHALL 仅存 env 变量名;其值 SHALL 经 `agent_secrets`(全系统 secret 的唯一密文信源)解析、node 中转、agent 进程以环境变量取用。本 change MUST NOT 为 MCP 鉴权另建任何 secret 存储路径。

#### Scenario: client_secret 值走 agent_secrets 而非注册表
- **WHEN** oauth_client_credentials 型 server 的 `client_secret_env="ACME_CS"`,管理员经 secret 接口设 `ACME_CS` 的值
- **THEN** 值密文存 `agent_secrets`,materialize/node 注入进 agent env;`mcp_servers` 表只持 `"client_secret_env":"ACME_CS"` 引用名

### Requirement: materialize 把 auth_type + auth_config 翻译为 agent.yaml 鉴权字段
materialize SHALL 把注册表的 `(auth_type, auth_config)` 翻译为 agent.yaml 的现有鉴权表示(`McpServerSettings.auth_type` / `api_key_env`,以及 oauth 的 `auth` 块);agent 侧 `McpServerSettings` schema 与 `integrations/mcp/client.py` 的消费 MUST NOT 因此改变。`oauth_authorization_code` 型 SHALL 翻译为 agent.yaml 的 authorization_code `auth` 块(authorization_endpoint/token_url/client_id/scope/redirect_path/client_secret_env),使 agent 侧按 per-user OAuth 路径发起授权。

#### Scenario: api_key 翻译进 agent.yaml
- **WHEN** materialize 一个 `auth_type=api_key`、`auth_config={"key_env":"MY_TOKEN"}` 的 server
- **THEN** 渲染的 agent.yaml 含 `auth_type: api_key` + `api_key_env: MY_TOKEN`,agent 侧 MCP client 照常发 `Authorization: Bearer`

#### Scenario: oauth 翻译进 agent.yaml auth 块
- **WHEN** materialize 一个 oauth_client_credentials server
- **THEN** 渲染的 agent.yaml 含 `auth` 块(grant=client_credentials + token_url/client_id/scope/client_secret_env),agent 侧按既有 OAuth 路径连接

#### Scenario: authorization_code 翻译进 agent.yaml auth 块
- **WHEN** materialize 一个 oauth_authorization_code server
- **THEN** 渲染的 agent.yaml 含 authorization_code `auth` 块(authorization_endpoint/token_url/client_id/scope/redirect_path/client_secret_env),agent 侧按 per-user OAuth authorization_code 路径发起授权

### Requirement: managed 模式支持 OAuth client_credentials 静态鉴权
managed 模式 SHALL 能为 MCP server 配置 `oauth_client_credentials` 静态鉴权并使其在运行 agent 上生效——闭合此前"平台表无 OAuth 列、`auth` 恒 None"导致的 managed 无入口缺口。api_key 型 SHALL 保持可用、不回归。

#### Scenario: managed 配 OAuth 型 MCP 可用
- **WHEN** 在 managed 模式为某 agent 配置一个 oauth_client_credentials 型 MCP server,并设好 client_secret 值
- **THEN** 该 agent 部署后能以机器身份完成 OAuth 并连上该 MCP server

#### Scenario: managed api_key 型不回归
- **WHEN** 一个既有 api_key 型 MCP server 经迁移折叠进 auth_config 后被 materialize
- **THEN** 渲染的 agent.yaml 鉴权与迁移前等价,api-key 连接照常工作

