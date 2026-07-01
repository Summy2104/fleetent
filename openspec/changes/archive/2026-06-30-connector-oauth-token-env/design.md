## Context

中立模型 `OAuthAuthorizationCodeMcpAuthConfig`（继承 `McpOAuthSettings`）已含 `token_env: str = ""`。运行时 `integrations/mcp/client.py` 对 `_is_per_user_stdio`（transport=stdio + per-user oauth）的 server，按 `_stdio_token_env_name(server) = server.token_env or "MCP_OAUTH_ACCESS_TOKEN"` 把该用户的 access token 注入子进程 env。materialize 把连接器 `auth_config` parse 成 `OAuthAuthorizationCodeMcpAuthConfig` 并赋给 `McpServerSettings.auth`，token_env 随 auth dump 进 agent.yaml。唯一断点：`connector_admin_api._normalized_auth_config` 的 oauth_authorization_code 分支没把 `token_env` 写进持久化的 auth_config（前端也无输入），导致经连接器只能用默认变量名。

## Goals / Non-Goals

**Goals:**
- 连接器 `oauth_authorization_code` 配置可携带可选 `token_env`，并经 create/edit 持久化进 `auth_config`。
- 前端表单暴露可选 `token_env` 输入。
- 任意 stdio per-user OAuth server 可通过连接器声明自己的 access-token 注入变量名；留空回落默认。

**Non-Goals:**
- 不改 per-user 子进程注入/刷新/重启运行时（已实现）。
- 不注入 refresh_token / client_secret 进子进程（安全：仅注入短时 access token，平台独占刷新）。
- 不改 materialize（已带 token_env）、不改 DB schema、不改其它 auth_type。
- 不在本 change 重配 google-drive 连接器（合并后单独）。

## Decisions

**D1：`token_env` 作为 `oauth_authorization_code` 的可选字段，默认空。**
- 空 → 运行时回落 `MCP_OAUTH_ACCESS_TOKEN`，向后兼容（已有 oauth_authz 连接器不受影响）。
- 与现有 6 字段并列加第 7 个，最小改动。

**D2：仅扩展 `_normalized_auth_config` 持久化 + 前端渲染两处。**
- 后端：分支返回值加 `"token_env": parsed.token_env`。
- 前端：类型 + AUTH_CONFIG_FIELDS + page.tsx 输入 + 提交分支 + i18n；非必填，不进可创建校验（authorization_endpoint+token_url+client_id 仍是必填）。

**D3：仅对 stdio 语义相关，但字段对 http oauth_authz 也无害（http 忽略 token_env）。** 故不按 transport 条件显隐 token_env 输入，统一在 oauth_authorization_code 字段组展示并标注"stdio per-user 用"。

## Risks / Trade-offs

- [用户误以为 http 也需 token_env] → label/placeholder 注明"stdio per-user OAuth 用；留空=默认 MCP_OAUTH_ACCESS_TOKEN"。
- [token_env 写错变量名 → server 拿不到 token] → 运行时行为，不在本 change；文案给默认值提示降低误填。
- [前后端字段漂移] → page.test 断言提交 payload 含 token_env；后端 unit 断言归一化持久化 token_env。

## Migration Plan

纯增量、可选字段，默认空，无 DB schema 变更、无数据迁移。已有连接器不受影响。回滚=还原两处代码。

## Open Questions

无。
