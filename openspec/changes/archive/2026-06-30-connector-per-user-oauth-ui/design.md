## Context

后端中立 auth 模型 `src/fleetent/mcp_auth_models.py` 已定义 5 种 `auth_type` 的判别联合，含 `OAuthAuthorizationCodeMcpAuthConfig`（per-user OAuth 2.1 授权码，PKCE，`client_secret_env` 可选）。`mcp-auth-config` spec 要求该 schema 是「validation / materialize 翻译 / 前端表单渲染」三处共用的单一真相源。但三处中：

- **validation** 已覆盖（`parse_mcp_auth_config` 能校验 `oauth_authorization_code`）；
- **materialize** 已覆盖（`platform/agent_lifecycle/materialize.py:350-396` 把该 auth_config 映射进 `McpServerSettings.auth`）；
- **前端表单渲染** 未覆盖（`frontend/src/features/connectors/api.ts` 的 `McpAuthType` 联合无该值，`mcp/page.tsx` 无下拉项/字段组）；
- **connector 落库归一化** 未覆盖（`platform/connector_management/connector_admin_api.py:_normalized_auth_config` 无 `OAuthAuthorizationCodeMcpAuthConfig` 分支，落 `return {}` 丢字段）。

运行时侧：standalone per-user OAuth 完整（authorization.py 生成带 PKCE/state 的链接、`emit_authorization_link` 投递、platform `/oauth/callback` 完成交换、`mcp_user_tokens` 加密存储、`ManagedUserTokenResolver` 读取）。`mcp-managed-oauth` 要求授权链接「经现有 IM 链 DM 给用户本人」。但 `outbound.make_mcp_authz_deliverer`（outbound.py:262-298）在 node-managed 运行时**无 fallback、只返回 None**——而对称的 `make_mcp_credential_deliverer`（outbound.py:301-344）已有 `is_node_managed_runtime() → notify_user` 分支。

## Goals / Non-Goals

**Goals:**
- 管理员经前端「添加 MCP 服务器」connector 表单可创建 `oauth_authorization_code` 类型的 MCP，并填写其字段集。
- connector 注册表正确持久化该类型的结构化非密字段（不丢字段），使物化与运行时可用。
- node-managed 运行时下，per-user OAuth 授权链接能 DM 投递给用户本人（与 per-user api-key 凭证链接对称）。

**Non-Goals:**
- 不改 OAuth 回调路由、code→token 交换/刷新、`ManagedUserTokenResolver`、state/pending-auth store、materialize 映射（均已就位）。
- 不改 `none / api_key / oauth_client_credentials / api_key_per_user` 的现有行为。
- 不拆分 per-user bearer / api-key（仍由 `api_key_per_user` + `header_style` 表达）。
- 不改 DB schema、不新增 config 命名空间。

## Decisions

**D1：`oauth_authorization_code` 作为独立 auth_type（方案A），不把两种 OAuth 合并为 grant 子选择器。**
- 理由：与后端判别联合一一对应（前后端同一真相源），改动最小、回归面最小；现有 `oauth_client_credentials` 不动。
- 备选（已否决）：单一「OAuth」+ grant 子选择器——需重构现有 client_credentials 渲染，回归风险高，且与后端两个独立 auth_type 不再对应。

**D2：前端字段组与必填校验对齐 `OAuthAuthorizationCodeMcpAuthConfig`/`McpOAuthSettings` 校验器。**
- 字段：`authorization_endpoint` / `token_url` / `client_id`（必填）、`client_secret_env`（可选，PKCE 公共客户端留空）、`scope` / `redirect_path`（可选）。
- 可创建判据要求 `authorization_endpoint`+`token_url`+`client_id` 非空，与后端 `_require_authorization_code_fields` 一致，避免提交后端 422。

**D3：后端归一化复用 `parse_mcp_auth_config` 的解析结果，新增 `OAuthAuthorizationCodeMcpAuthConfig` 分支显式列出持久化字段。**
- 与现有 `OAuthClientCredentialsMcpAuthConfig` 分支同构，只持久化非密字段 + env 引用名；secret 值不入表。

**D4：managed authz deliverer fallback 直接复刻 credential deliverer 的结构。**
- 在 `make_mcp_authz_deliverer` 内：有 live connector → `send_to`（既有）；否则 `is_node_managed_runtime()` → `outbound_connectors.notify_user(user_id, msg)` 入队 directed-reach DM；都不可达 → 返回 False（不抛）。保持「谁也不依赖 platform import」的边界。

## Risks / Trade-offs

- [前端可创建校验与后端校验器漂移] → 用与后端相同的必填集（authorization_endpoint+token_url+client_id），并在 page.test.tsx 断言提交 payload，降低漂移。
- [managed deliverer 改动影响既有 standalone 投递路径] → 仅新增 fallback 分支，standalone（有 connector）路径不变；unit 测试分别覆盖 standalone 与 managed 两分支。
- [i18n 漏键导致前端渲染空白] → 中英文 messages 同步新增，page.test 通过文案/aria-label 命中。

## Migration Plan

纯增量，无 DB schema 变更、无数据迁移。部署后既有 connector 不受影响；新 auth_type 仅在管理员主动选择时生效。回滚 = 还原三处代码改动即可，无残留状态。合并到 main 后需重启 platform/node 方可在运行实例生效（本 change 不负责重启）。

## Open Questions

无。范围、auth_type 终态、方案A 已与 stakeholder（项目 owner）确认。
