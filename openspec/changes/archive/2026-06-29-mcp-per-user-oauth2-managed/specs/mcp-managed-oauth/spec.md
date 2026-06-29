## ADDED Requirements

### Requirement: managed 下缺 per-user token 经 platform 回调完成授权

managed 部署下,当一个 per-user OAuth(authorization_code)MCP 服务被某用户调用而该 `(user, agent, server)` 无有效 token 时,系统 SHALL 复用与 standalone 一致的发起逻辑(D6 生成带 PKCE 与绑定 state 的授权链接、经现有 IM 链 DM 给用户本人),且授权链接的 `redirect_uri` MUST 指向 **platform** 公开回调而非 agent 自身。agent runtime MUST NOT 因此 import platform,MUST NOT 直连 platform。

#### Scenario: managed 无 token 触发授权且回调指向 platform
- **WHEN** managed 下某用户调用一个 per-user oauth 的 MCP 服务且其三元组无有效 token
- **THEN** 返回明确的「需授权」结果(不抛异常、不卡住),并 DM 该用户一个授权链接,其 `redirect_uri` 指向 platform 公开回调

#### Scenario: 授权发起逻辑与 standalone 同源
- **WHEN** 比较 managed 与 standalone 两态生成授权链接的协议逻辑
- **THEN** 二者共用同一 PKCE/state/URL 构建纯逻辑(D6),仅 `redirect_uri` 落点不同

### Requirement: agent 经 node 向 platform 登记 pending-auth

agent 在发出授权链接前 SHALL 把该次授权的 `state → (code_verifier, user_id, agent_id, server_id, token_url, client_id, client_secret_env)` 经 node 转发到 platform 登记为 pending-auth,使 platform 回调时能反查并完成 code 交换。pending-auth MUST 短 TTL、一次性消费;`code_verifier` 经此通道一次性下发到 platform,MUST NOT 落 agent 持久层。

#### Scenario: 发链接前登记 pending-auth
- **WHEN** agent 为某三元组生成授权链接
- **THEN** 先经 node→platform `POST /nodes/{id}/mcp/oauth-pending` 登记 `state→(code_verifier, 三元组, token 端点/client)`,platform 短 TTL 存储该记录

#### Scenario: pending-auth 一次性且过期失效
- **WHEN** 同一 state 的回调到达两次,或在 TTL 之后到达
- **THEN** 仅首次有效;重复或过期的 state 被拒绝、不完成交换

### Requirement: platform 公开回调完成 code→token 并存管理库

platform SHALL 暴露公开路由 `GET /oauth/callback`,以回调带回的 `state` 反查 pending-auth(MUST NOT 依赖回调请求的登录态),用 D6 纯逻辑以 `code` + `code_verifier` 向 token 端点交换 access+refresh token,并 SHALL 把 token 密文存入管理库 `mcp_user_tokens`,按 `(user_id, agent_id, server_id)` 三元组键隔离。交换所用 client_secret SHALL 经 `agent_secrets` 由 `client_secret_env` 解析,MUST NOT 入 `mcp_user_tokens` 或注册表。

#### Scenario: 回调以 state 反查并换 token 入管理库
- **WHEN** 用户在浏览器完成授权,授权服务器重定向回 platform `/oauth/callback?code&state`
- **THEN** platform 校验 state → 反查三元组与 code_verifier → 换取 access+refresh token → 密文存管理库 `mcp_user_tokens`(三元组键);state 随即作废

#### Scenario: 三元组隔离
- **WHEN** 同一用户对两个不同 agent 授权同一 MCP server
- **THEN** 两条 token 记录按各自三元组独立存储,互不可见、互不复用

### Requirement: node↔platform per-user token 端点

平台 SHALL 暴露 `POST /nodes/{id}/mcp/oauth-pending` 与 `POST /nodes/{id}/mcp/oauth-token` 两个端点,与既有 `/nodes/{id}/identity/resolve` 同族,由 node 持 service key 调用(MUST 鉴权 node 身份)。`oauth-token` SHALL 按三元组返回有效 access token;当存储的 access token 已过期且持有 refresh token 时,SHALL 在 platform 侧用 refresh token 透明刷新后返回新 access token。返回体 MUST NOT 含 refresh_token。

#### Scenario: 取 token 端点返回有效 access token
- **WHEN** node 持 service key 调 `POST /nodes/{id}/mcp/oauth-token` 带某三元组
- **THEN** platform 返回该三元组的有效 access token(必要时先透明刷新),返回体不含 refresh_token

#### Scenario: 端点拒绝非 node 调用
- **WHEN** 不带合法 node service key 调用上述端点
- **THEN** 返回鉴权失败,不泄露 token

### Requirement: agent→node 同步 loopback 通道取 token

managed 下 agent SHALL 经一条**仅本机的同步 loopback 通道**向 node 请求 per-user token(pending 登记与 token 取用),node 收到后持 service key 转发到对应 platform 端点。该通道地址与凭据 SHALL 由 node 在 spawn agent 时经环境注入;通道 MUST 仅服务 oauth-pending/oauth-token 两类请求,MUST NOT 让 agent 获得 platform 地址或凭据、MUST NOT 使 agent import platform。

#### Scenario: agent 经 loopback 通道同步取 token
- **WHEN** managed agent 的 resolver 需要某三元组的 token
- **THEN** 经注入的本机 loopback 通道请求 node → node 转发 platform `oauth-token` → 同步返回 access token 给 agent

#### Scenario: 通道凭据缺失或非法被拒
- **WHEN** 对 node loopback 通道的请求未带 spawn 注入的凭据
- **THEN** node 拒绝该请求,不转发 platform

### Requirement: agent managed 注入 resolver 并进程内短 TTL 缓存

managed 启动 SHALL 经 `set_user_token_resolver` 注入一个走 loopback 通道取 token 的 resolver;agent SHALL 在进程内按三元组短 TTL 缓存 access token,缓存未命中、过期、或 MCP 服务返回 `401` 时 SHALL 经通道重取。注入的 resolver 返回的 `UserToken` MUST 仅含 access_token(refresh_token 为 None),使 refresh_token 不出 platform。未注入 resolver(standalone)时 MUST 回落切片 1 的本地 token 库,行为不变。

#### Scenario: 缓存命中不打 node
- **WHEN** 某三元组的 access token 在缓存中且未临近过期
- **THEN** agent 直接用缓存 token,不经 loopback 通道

#### Scenario: 过期或 401 触发重取
- **WHEN** 缓存 token 过期,或 MCP 服务对携带的 token 返回 401
- **THEN** agent 经通道重取(platform 端必要时透明刷新),用新 token 重试

#### Scenario: 未注入 resolver 时回落本地(standalone 不变)
- **WHEN** 进程未注入 per-user token resolver
- **THEN** token 解析回落切片 1 的本地加密库,standalone 行为与切片 1 一致

### Requirement: 管理库 mcp_user_tokens 由 Alembic 维护且密文存储

per-user token 的 managed 存储 SHALL 落在管理库新增表 `mcp_user_tokens`,schema MUST 由 Alembic 迁移维护(不在 store 内建表),按 `(user_id, agent_id, server_id)` 三元组键。access_token / refresh_token / expiry / scope MUST 密文存储,SQL MUST 用 named parameters 经 store 边界。refresh_token MUST NOT 经任何 API 返回出 platform。

#### Scenario: token 密文落管理库 Alembic 表
- **WHEN** platform 回调换得 token
- **THEN** 以三元组键密文写入管理库 `mcp_user_tokens`(Alembic 表),refresh_token 仅留库内、不经接口外泄
