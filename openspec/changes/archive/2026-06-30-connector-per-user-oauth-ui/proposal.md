## Why

平台「添加 MCP 服务器」connector 表单的鉴权类型只暴露 `none / api_key / oauth_client_credentials / api_key_per_user` 四种，**缺 per-user OAuth 2.1 授权码（`oauth_authorization_code`，动态授权）**。但中立 auth 模型 `mcp_auth_models.py` 早已定义该类型，`mcp-auth-config` 也已要求该判别联合 schema 是「validation / materialize / 前端表单渲染」三处共用的单一真相源——三处中却有两处（前端渲染、connector 落库归一化）未落实它，且 managed 运行时的授权链接投递无 fallback。结果：管理员无法经 UI 创建 per-user OAuth 的 MCP，强行配置也会落库丢字段、托管模式下授权链接送不到用户。本 change 把这三处实现补齐到已有 spec 要求。

## What Changes

- **前端 connector 表单新增 `oauth_authorization_code` 鉴权类型**：`McpAuthType` 联合加该值；鉴权类型下拉新增「OAuth 授权码（按用户动态授权）」；新增字段组 `authorization_endpoint / token_url / client_id / client_secret_env(可选, PKCE 公共客户端可空) / scope / redirect_path`；`AUTH_CONFIG_FIELDS` 映射、提交 payload 分支、可创建校验（`authorization_endpoint`+`token_url`+`client_id` 必填）、中英文 i18n 文案。
- **后端 connector 落库归一化补齐**：`connector_admin_api._normalized_auth_config` 新增 `OAuthAuthorizationCodeMcpAuthConfig` 分支，持久化 `token_url / client_id / client_secret_env / scope / authorization_endpoint / redirect_path`（现状落 `return {}` 丢全部字段，连带物化校验失败）。
- **managed 授权链接投递补齐**：`outbound.make_mcp_authz_deliverer` 补上与 `make_mcp_credential_deliverer` 对称的 managed 分支——`is_node_managed_runtime()` 时经 `outbound_connectors.notify_user` 入队 directed-reach DM（现状 managed 下无 fallback、只返回 None，授权链接送不到用户本人）。
- 不改动 `none / api_key / oauth_client_credentials / api_key_per_user` 既有行为；不改 DB schema；不新增 config 命名空间。

## Capabilities

### New Capabilities
<!-- 无新能力；全部为对既有 spec 的一致性补齐 -->

### Modified Capabilities
- `mcp-auth-config`: 明确判别联合 schema 的「前端表单渲染」与「connector 落库归一化」两个消费方 MUST 覆盖 `oauth_authorization_code`——前端可选择该类型并填其字段集，connector 注册表 MUST 持久化其结构化非密字段（不得丢成空），与既有 `oauth_client_credentials / api_key_per_user` 一致。
- `mcp-managed-oauth`: 明确 per-user OAuth 授权链接在 **node-managed 运行时** MUST 经 directed-reach（`notify_user`）DM 投递给用户本人——与 per-user api-key 的凭证表单链接投递对称，补齐既有「DM 给用户本人」要求在托管态的落地。

## Impact

- **受影响代码**：
  - 前端 `frontend/src/features/connectors/api.ts`、`frontend/src/features/mcp/page.tsx`、`frontend/src/i18n/messages.ts`（+ `page.test.tsx`）。
  - 后端 `src/fleetent/platform/connector_management/connector_admin_api.py`（`_normalized_auth_config`）。
  - 顶层 `src/fleetent/outbound.py`（`make_mcp_authz_deliverer`）。
- **Public API surface**：connector admin REST（`McpServerCreateBody/EditBody` 接受 `auth_type=oauth_authorization_code` + 对应 `auth_config` 字段）；前端 connector API client 类型。
- **owning packages**：frontend(connectors/mcp feature)、`platform.connector_management`、顶层 `outbound.py`。
- **owned tables**：无新增（复用既有 `mcp_server` / `mcp_user_tokens`，均在 management.db）。
- **config namespace**：无新增。
- **cross-module deps**：`outbound → outbound_connectors`（既有）、`connector_admin_api → mcp_auth_models`（既有）；不新增反向依赖；agent 侧不 import platform。
- **migration / shim plan**：无（纯增量，不改 schema、不改现有 auth_type 语义）。
- **明确不在范围（已就位，不动）**：OAuth 回调路由（platform `/oauth/callback`）、code→token 交换与刷新、`ManagedUserTokenResolver`、state/pending-auth store、connector→agent 物化映射（`materialize.py` 已处理 `OAuthAuthorizationCodeMcpAuthConfig`）。
