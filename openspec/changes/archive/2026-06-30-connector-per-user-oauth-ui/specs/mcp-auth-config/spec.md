## ADDED Requirements

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
