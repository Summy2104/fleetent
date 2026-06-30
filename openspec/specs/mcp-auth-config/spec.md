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

### Requirement: MCP 鉴权 secret 经 agent_secrets 唯一信源,平台不持明文
`auth_config` 中的 secret 字段 SHALL 仅存 env 变量名;其值 SHALL 经 `agent_secrets`(全系统 secret 的唯一密文信源)解析、node 中转、agent 进程以环境变量取用。本 change MUST NOT 为 MCP 鉴权另建任何 secret 存储路径。

#### Scenario: client_secret 值走 agent_secrets 而非注册表
- **WHEN** oauth_client_credentials 型 server 的 `client_secret_env="ACME_CS"`,管理员经 secret 接口设 `ACME_CS` 的值
- **THEN** 值密文存 `agent_secrets`,materialize/node 注入进 agent env;`mcp_servers` 表只持 `"client_secret_env":"ACME_CS"` 引用名

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

### Requirement: managed 模式支持 OAuth client_credentials 静态鉴权
managed 模式 SHALL 能为 MCP server 配置 `oauth_client_credentials` 静态鉴权并使其在运行 agent 上生效——闭合此前"平台表无 OAuth 列、`auth` 恒 None"导致的 managed 无入口缺口。api_key 型 SHALL 保持可用、不回归。

#### Scenario: managed 配 OAuth 型 MCP 可用
- **WHEN** 在 managed 模式为某 agent 配置一个 oauth_client_credentials 型 MCP server,并设好 client_secret 值
- **THEN** 该 agent 部署后能以机器身份完成 OAuth 并连上该 MCP server

#### Scenario: managed api_key 型不回归
- **WHEN** 一个既有 api_key 型 MCP server 经迁移折叠进 auth_config 后被 materialize
- **THEN** 渲染的 agent.yaml 鉴权与迁移前等价,api-key 连接照常工作

### Requirement: connector 落库与前端表单 MUST 覆盖 oauth_authorization_code

判别联合 schema 既是 validation / materialize / 前端表单渲染的单一真相源，则其 `oauth_authorization_code` 类型的两个尚未落实的消费方 SHALL 与既有 `oauth_client_credentials` / `api_key_per_user` 一致地覆盖：

- **connector 落库归一化**：connector 注册表写入路径（create / edit）SHALL 持久化 `oauth_authorization_code` 的结构化非密字段 `authorization_endpoint` / `token_url` / `client_id` / `scope` / `redirect_path` 与 secret 的 env 引用名 `client_secret_env`，MUST NOT 丢成空对象。secret 的**值** MUST NOT 入表。
- **前端表单渲染**：管理「添加 MCP 服务器」表单 SHALL 把 `oauth_authorization_code` 列为可选鉴权类型，并在选中时渲染上述字段集；提交前 SHALL 校验 `authorization_endpoint` + `token_url` + `client_id` 非空（与后端 authorization_code 校验器一致），`client_secret_env` 可留空（OAuth 2.1 公共客户端 + PKCE）。

#### Scenario: connector 落库保留 authorization_code 结构化字段

- **WHEN** 管理员经 connector 注册表以 `auth_type=oauth_authorization_code` 提交 `authorization_endpoint` / `token_url` / `client_id` / `scope` / `redirect_path` 与 client_secret 的 env 名
- **THEN** 注册表 `auth_config` 持久化以上非密字段与 `client_secret_env`，不为空对象，且 client_secret 值不入表

#### Scenario: 前端表单暴露 oauth_authorization_code 并校验必填

- **WHEN** 管理员在「添加 MCP 服务器」表单选择 `oauth_authorization_code`
- **THEN** 表单渲染 `authorization_endpoint` / `token_url` / `client_id` / `client_secret_env`(可选) / `scope` / `redirect_path` 字段，且在 `authorization_endpoint`、`token_url`、`client_id` 任一为空时禁止提交

#### Scenario: 提交 payload 携带结构化 auth_config

- **WHEN** 管理员填齐必填字段并提交
- **THEN** 前端发往 connector admin REST 的请求体 `auth_type=oauth_authorization_code`，`auth_config` 含已填的 authorization_endpoint / token_url / client_id / client_secret_env / scope / redirect_path

### Requirement: oauth_authorization_code 连接器 MUST 支持可选 token_env

`oauth_authorization_code` 类型用于 stdio per-user OAuth 时，运行时按该 server 的 `token_env` 环境变量名把每个用户的短时 access token 注入其专属子进程（留空回落默认 `MCP_OAUTH_ACCESS_TOKEN`）。为让任意 stdio per-user OAuth server 可声明各自的注入变量名，连接器配置面 SHALL 覆盖可选字段 `token_env`：

- **connector 落库归一化**：connector 注册表的 create / edit 路径 SHALL 持久化 `oauth_authorization_code` 的可选非密字段 `token_env`（默认空字符串），与既有 `authorization_endpoint` / `token_url` / `client_id` / `client_secret_env` / `scope` / `redirect_path` 并列，MUST NOT 丢弃。
- **前端表单**：管理「添加/编辑 MCP 服务器」表单在 `oauth_authorization_code` 字段组 SHALL 提供一个**可选** `token_env` 输入（标注用于 stdio per-user OAuth、留空=默认 `MCP_OAUTH_ACCESS_TOKEN`），并随提交 payload 与编辑回填。`token_env` MUST NOT 成为可创建必填项（必填仍为 `authorization_endpoint` + `token_url` + `client_id`）。
- 留空时行为 MUST 与现状一致（向后兼容；已有 oauth_authz 连接器不受影响）。

#### Scenario: connector 落库保留 token_env

- **WHEN** 管理员以 `auth_type=oauth_authorization_code` 提交并填写 `token_env`（如 `GOOGLE_DRIVE_MCP_ACCESS_TOKEN`）
- **THEN** 注册表 `auth_config` 持久化 `token_env`，与其它 oauth 字段并存，不被丢弃

#### Scenario: token_env 可留空且向后兼容

- **WHEN** 管理员提交 `oauth_authorization_code` 但不填 `token_env`
- **THEN** 归一化得到 `token_env` 为空字符串，连接器可正常创建，运行时回落默认注入变量名

#### Scenario: 前端表单暴露可选 token_env 并随 payload 提交

- **WHEN** 管理员在表单选择 `oauth_authorization_code` 并填写 token_env 后提交
- **THEN** 表单渲染该可选输入，发往 connector admin REST 的 `auth_config` 含所填 `token_env`；且 token_env 为空不影响提交（不计入必填校验）

