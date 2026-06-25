## Why

当前 MCP 的 OAuth2 只实现了 **client_credentials**(机器身份)：同一 agent 下所有用户共享一条会话、一套凭据,MCP server 永远看到 agent 的机器身份,无法做到"不同用户以各自身份访问同一个 MCP server"。对接 OAuth 2.1 的 per-user 资源(用户各自的私有数据)时,这是硬缺口。

本变更引入 **per-user OAuth 2.1 Authorization Code(用户委托)授权**:每个用户以自己的身份授权一次,之后 agent 以该用户身份访问 MCP server,按 `(user, agent, server)` 隔离,streamable http 与 stdio 双传输都支持。

本变更落地**切片 1:共享核 + standalone 实现**——让 per-user OAuth 在无 platform 的 standalone 部署即可工作,并把注入缝留给后续 managed 切片。

## What Changes

- **新增 per-user OAuth 2.1 Authorization Code 授权**(用户委托 token,区别于现有 client_credentials 机器身份)。
- **token 按 `(user_id, agent_id, server_id)` 隔离**:agent1 的授权不可用于 agent2;同一用户对每个 agent 各授权一次。
- **MCP 会话/子进程按用户隔离**:
  - http:会话 key 由 `(scope, server_id)` 扩为 `(scope, server_id, user_id)`,每用户一条 ClientSession,自定义 `httpx.Auth` 逐请求带该用户 Bearer。
  - stdio:标准 env 认证 server 下,不同用户 = 不同子进程(per-user,非 per-call;同用户并发复用同进程),token 进子进程 env,子进程寿命 ≤ token 有效期,过期/401 重启;空闲池 + 超时回收 + owner-task 信号关闭 + 总量/每用户上限 + 孤儿回收。
- **无 token 触发授权**:`call_tool` 命中无 token 时不报错,返回"需授权"结果(挂 degrade 链),由 agent 经 IM 发 Authorization Code + PKCE 授权链接(state 绑 `user×agent×server`,一次性 + 短 TTL),用户浏览器授权后回调入库。
- **注入缝 `set_user_token_resolver`**(仿 `set_im_identity_resolver`):agent 侧 MCP client 经注入的 resolver 按 user 取 token;standalone 留本地实现,managed(切片 2)注入 platform/node 实现。
- **standalone 实现**:agent 自挂 `/oauth/callback`、本地加密 token 表(嵌入式 forward-only 迁移)、agent 自刷新、用自身 IM 连接器发授权链接。
- 迁移 streamablehttp 已弃用 API:`streamablehttp_client(headers=,auth=)` → `streamable_http_client(url, http_client=<带 auth 的 AsyncClient>)`,保留 re-export shim。
- **非破坏**:无 per-user OAuth 配置的 MCP server 行为不变;旧 `(scope, server_id)` 调用经会话 key 扩维保持兼容;client_credentials 路径保留。

## Capabilities

### New Capabilities
- `mcp-per-user-oauth`: per-user OAuth 2.1 Authorization Code 授权流程(无 token 触发、PKCE+state 授权链接、code 交换、按 `user×agent×server` 隔离的 token 存储与刷新、注入缝 `set_user_token_resolver`、standalone 自托管回调与本地库)。
- `mcp-per-user-session`: MCP 会话/子进程按用户隔离与生命周期(http per-user ClientSession + 自定义逐请求 auth;stdio per-user 子进程池 + 空闲回收 + owner-task 信号关闭 + 上限 + 孤儿回收;token 过期驱动的刷新/重启)。

### Modified Capabilities
- `mcp-oauth2-auth`: 在现有 client_credentials 之外新增 **authorization_code(用户委托)** grant,并引入 `set_user_token_resolver` 注入缝;client_credentials 行为保持不变。

## Impact

- **owning packages**: `integrations/mcp`(per-user session + resolver 缝 + 授权触发)、`runtime`/`server`(standalone 下 agent 自挂 `/oauth/callback`)、`db`/agent 侧嵌入式迁移(本地 token 表)。
- **owned tables**: standalone agent 本地库新增 per-user MCP token 表(嵌入式 forward-only 迁移);managed 的管理库 `mcp_user_tokens`(Alembic)留待切片 2。
- **public API surface**: `mcp_client.set_user_token_resolver(resolver)`;standalone agent HTTP 新增 `GET /oauth/callback`。
- **config namespace**: `agent.yaml` 的 `mcp_servers[].auth` 扩展 oauth2 authorization_code 字段(authorization_endpoint / token_url / client_id / client_secret_env / scope / redirect_path)。
- **契约守护**: agent runtime 仍禁止 import platform;agent 数据不写 platform 表;refresh_token 在 standalone 由 agent 自持(单进程单信任域),managed 切片再保证 refresh_token 不出 platform。
- **后续切片(不在本变更)**: 切片 2 = managed 实现(platform 回调/库/refresh/撤销 + 管理库 `mcp_user_tokens`[Alembic] + node API `POST /nodes/{id}/mcp/oauth-token` + agent→node 同步取 token 通道 + 短 TTL 缓存),挂同一注入缝。
