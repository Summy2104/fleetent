## ADDED Requirements

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
