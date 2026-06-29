## Why

切片 1(`mcp-per-user-oauth2`)已让 per-user OAuth 2.1 authorization_code 在 **standalone** 部署跑通(agent 自挂回调 + 本地加密 token 库 + 自刷新),并留下注入缝 `set_user_token_resolver`。但 **managed 部署**下 agent 以 `--no-im` 运行、无 platform 凭据、不持公开 ingress,缺一条让 agent 经 node 从 platform 取 per-user token 的链路——注入缝至今空挂,managed 下 per-user OAuth 无法工作。本切片补齐 managed 实现,且不破坏 standalone。

## What Changes

- 把 MCP 鉴权配置 schema(`auth_type` discriminated union + `auth_config`)从 `platform/connector_management/mcp_auth.py` 提取到 **agent 与 platform 都能 import 的中立模块**,新增 `auth_type=oauth_authorization_code` variant(`authorization_endpoint` / `token_url` / `client_id` / `client_secret_env` / `scope` / `redirect_path`);`client_id` 支持 `${ENV}` 引用解析。原文件留 **re-export shim**,既有 import 不破坏。
- platform 侧(`platform/connector_management`)新增 per-user OAuth token 经纪:公开 `GET /oauth/callback` 落点、`POST /nodes/{id}/mcp/oauth-pending`(登记 `state→(code_verifier, user×agent×server, token 端点/client)`,短 TTL、一次性)、`POST /nodes/{id}/mcp/oauth-token`(按三元组取 access token,过期则用 refresh token 透明刷新后返回)。
- 管理库新增 `mcp_user_tokens` 表(Alembic,接 110 之后),密文存 access/refresh/expiry/scope,按 `(user_id, agent_id, server_id)` 三元组键。**refresh_token 与 client_secret 永不出 platform**。
- node 侧新增 **agent→node 同步 loopback 小通道**:node spawn agent 时经 env 注入该通道地址 + 凭据;node 持 service key 把 agent 的 pending/token 请求转发到上述两个 platform 端点。
- agent 侧 managed 启动注入 `set_user_token_resolver`:resolver 走同步通道取 token,**agent 进程内短 TTL 缓存**,过期 / MCP 返回 401 时重取。授权发起逻辑(D6 建 URL + PKCE + state、`redirect_uri`=platform 回调、经 node 登记 pending、经现有 IM 链 DM 链接给用户)**与 standalone 一致**,仅 `redirect_uri` 指向 platform。
- code→token 交换、refresh、PKCE/state 校验 **复用切片 1 的纯逻辑模块(D6)**,managed 与 standalone 共用。

## Capabilities

### New Capabilities
- `mcp-managed-oauth`: managed 部署下的 per-user OAuth token 经纪——platform 公开回调 + code→token 交换 + 透明刷新 + 管理库 `mcp_user_tokens` 存储;node↔platform 两个 `/nodes/{id}/mcp/oauth-*` 端点;agent→node 同步 loopback 通道;agent managed 注入 resolver + 进程内短 TTL 缓存 + 401/过期重取;refresh_token/client_secret 不出 platform。

### Modified Capabilities
- `mcp-auth-config`: discriminated union 新增 `oauth_authorization_code` 类型;鉴权 schema 提取到 agent/platform 共用的中立模块(agent 侧消费不再依赖 platform 包);`client_id` 支持 env 引用解析。

## Impact

- **新增中立包**(共享鉴权 schema)+ `platform/connector_management/mcp_auth.py` 留 re-export shim。
- **platform/connector_management**:`/oauth/callback` 路由、两个 node 端点、`mcp_user_tokens` store + Alembic 迁移(110+)、pending-auth 短 TTL 存储。
- **node/**:agent→node loopback 同步通道 + 转发到 platform 端点;spawn agent 时注入通道 env。
- **integrations/mcp**:managed resolver(经同步通道)+ 进程内短 TTL 缓存;授权发起 `redirect_uri` 在 managed 指向 platform 回调。standalone 路径(`mcp-per-user-oauth` 切片 1)行为不变。
- **复用**:切片 1 的 D6 纯逻辑模块、`set_user_token_resolver` 注入缝、`UserToken`/`UserTokenStore` 抽象。
- **契约守护**:agent runtime 仍 MUST NOT import platform;agent→platform 只经 node;agent 数据不写 platform 表;refresh_token/client_secret 不出 platform。
- **Non-Goals**:撤销(revocation,后续单独切片)、standalone 行为变更、MCP server 端实现。
