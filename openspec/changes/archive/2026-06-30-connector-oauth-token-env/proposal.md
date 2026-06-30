## Why

stdio 传输的 per-user OAuth 2.1 服务（`auth_type=oauth_authorization_code`）靠 fleetent 在 spawn 子进程时把**该用户的短时 access token** 注入一个环境变量——变量名由 `McpOAuthSettings.token_env` 指定（空则用默认 `MCP_OAUTH_ACCESS_TOKEN`）。运行时（per-user 子进程池、注入、过期重启）已具备，模型 `OAuthAuthorizationCodeMcpAuthConfig` 也继承了 `token_env`。但**连接器配置面没有暴露 `token_env`**：`connector_admin_api._normalized_auth_config` 的 oauth_authorization_code 分支只持久化 6 个字段、丢掉 `token_env`，前端表单也无该输入。结果：经连接器配置的 stdio per-user OAuth server，只能用默认 `MCP_OAUTH_ACCESS_TOKEN`；凡是读其它变量名的 server（如 `@piotr-agier/google-drive-mcp` 读 `GOOGLE_DRIVE_MCP_ACCESS_TOKEN`）都拿不到注入的 token。补上 `token_env` 即可让**任意** stdio per-user OAuth server 经连接器通用配置，且仍只注入短时 token、refresh_token/secret 不进子进程。

## What Changes

- **后端归一化**：`connector_admin_api._normalized_auth_config` 的 `OAuthAuthorizationCodeMcpAuthConfig` 分支新增持久化 `token_env`（可选，默认空字符串）。
- **前端**：`connectors/api.ts` 的 `McpOAuthAuthorizationCodeAuthConfig` 增加 `token_env`；`AUTH_CONFIG_FIELDS.oauth_authorization_code` 增加 `token_env`；`mcp/page.tsx` 在 oauth_authorization_code 字段组增加一个**可选** `token_env` 输入（提示：stdio per-user OAuth 时填 server 读取 access token 的环境变量名，留空=默认 `MCP_OAUTH_ACCESS_TOKEN`），提交 payload、编辑回填、i18n（中英文）。
- 不改运行时（per-user 子进程注入已实现）、不改 DB schema、不改其它 auth_type 行为；`token_env` 为纯增量可选字段。materialize 已将 `OAuthAuthorizationCodeMcpAuthConfig.token_env` 带入 agent.yaml `auth.token_env`，无需改动。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `mcp-auth-config`: 明确 `oauth_authorization_code` 类型的连接器落库归一化与前端表单 SHALL 覆盖可选字段 `token_env`（stdio per-user OAuth 的 access-token 注入变量名），使任意 stdio per-user OAuth server 可声明各自的注入变量名；留空时回落运行时默认。

## Impact

- **受影响代码**：前端 `frontend/src/features/connectors/api.ts`、`frontend/src/features/mcp/page.tsx`、`frontend/src/i18n/messages.ts`（+ `page.test.tsx`）；后端 `src/fleetent/platform/connector_management/connector_admin_api.py`（`_normalized_auth_config`）。
- **Public API surface**：connector admin REST 的 `oauth_authorization_code` `auth_config` 新增可选 `token_env`；前端 connector API client 类型。
- **owning packages**：frontend(connectors/mcp feature)、`platform.connector_management`。
- **owned tables**：无新增（复用 `mcp_servers.auth_config`）。
- **config namespace**：无新增。
- **cross-module deps**：无新增（`token_env` 已在中立模型 `McpOAuthSettings`/`OAuthAuthorizationCodeMcpAuthConfig`）。
- **migration / shim plan**：无（纯增量、可选字段，默认空）。
- **不在范围**：per-user 子进程注入/刷新运行时（已实现）、materialize 映射（已支持 token_env）、其它 auth_type、google-drive 连接器的实际重配（合并后单独做）。
