# 问题与决策点 — mcp-sdk-oauth-provider(供审核)

本文件记录从 A(自定义 httpx.Auth)切换到 B(SDK `ClientCredentialsOAuthProvider`)过程中,所有自行做出的决策、踩到的问题、以及行为变化。**请重点审核 D1 与 R1——它们是 B 相对 A 的实质行为改变。**

---

## 背景

- 上一个 change(`mcp-sdk-oauth`,已合并)用 fleetent 自写的 `_ClientCredentialsAuth` 处理 oauth2 client_credentials,手写 token POST。
- 经核查,官方 SDK 1.27.2 自带 `mcp.client.auth.extensions.client_credentials.ClientCredentialsOAuthProvider`(本身是 `httpx.Auth`),能做 client_credentials 并附带 RFC 8707 受众绑定等标准特性。
- 用户决定:采用 B(preseed 变体),保留 fleetent 显式 `token_url` 模型。

---

## 决策点

### D1.(最重要)B 是反应式 401 流程,不是主动挂 token —— 接受并保留
- **事实**(`oauth2.py:491-605`):SDK provider 每次请求,若有有效缓存 token 就主动挂;否则**发不带 token 的请求 → 等服务端 401 → 才发现 + 取 token + 重试**。冷启动 / token 过期后都先白发一个 401。
- **对比 A**:A 每次请求前就把有效 token 挂上,从不发无 token 请求,不依赖 401。
- **决策**:接受 B 的反应式流程(这是采用 SDK provider 的内在代价,绕开它=重写整个 auth_flow=退化回 A)。
- **影响**:① 每个新会话首个请求 + 每次 token 过期后,多一次 "tokenless→401→reauth" 往返;② **要求 MCP 服务端必须用 401 触发认证**。

### D2. 用 preseed 保留显式 `token_url`,而非强制发现 —— 选 preseed
- **问题**:SDK provider 构造只收 `server_url`,token 端点靠 `.well-known` 发现或回退 `{server}/token`,**不收独立 token_url**。fleetent 用显式独立 `token_url`。
- **决策**:子类 `_initialize` 里预填 `context.oauth_metadata = OAuthMetadata(issuer, authorization_endpoint, token_endpoint=token_url)`,issuer/authz 从 token_url 的 scheme+host 派生(占位、client_credentials 不用)。`_get_token_endpoint` 优先用 metadata.token_endpoint → 命中预填的 token_url。
- **效果**:取 token 去显式 token_url;若服务端**确实**暴露发现,发现结果会覆盖预填(发现优先,token_url 兜底)——是个合理的混合。

### D3. 客户端认证方法用 `client_secret_post`(而非 SDK 默认 basic)
- **问题**:A 把 client_id/secret 放在 POST body(=`client_secret_post`)。SDK 扩展默认 `client_secret_basic`(HTTP Basic 头)。
- **决策**:`token_endpoint_auth_method="client_secret_post"`,与 fleetent 既有线缆行为一致,避免对(未来的)token 端点造成预期外的认证方式变化。后续若需要 basic,可加 server 级配置(YAGNI,暂不做)。

### D4. 保留 sticky/transient 区分 —— 覆盖 `_handle_token_response`
- **问题**:SDK 的 `_handle_token_response`(`oauth2.py:409-414)对**任何**非 200 一律 `raise OAuthTokenError`,**不区分**真认证错(invalid_client/invalid_grant)与瞬时错(5xx/网络)。但 mcp-oauth2-auth spec 明确要求:真认证错→sticky 标记不可用、不反复重试;瞬时错→可重试、不标记。
- **决策**:子类覆盖 `_handle_token_response`:状态 400/401 且响应体含 invalid_client/invalid_grant → 置 `server._auth_unavailable=True`(副作用)并抛 `OAuthAuthUnavailableError`(sticky 信号);其余非 200 → 交回 super 抛 `OAuthTokenError`(瞬时、可重试)。这样 A 原有的 sticky/transient 语义完整保留。

### D5. 调用路径错误映射 —— 用 sticky 副作用 + 类型双保险
- **问题**:SDK 的 OAuth 异常经 ClientSession.call_tool 冒泡,可能被 anyio 包裹,直接 `except OAuthAuthUnavailableError` 可能漏。
- **决策**:`_call_via_session`/`_call_utility` 捕获异常后:① 先看 `server._auth_unavailable`(D4 的副作用,抗包裹)→ 返回"认证不可用"降级文案;② 否则若是 SDK OAuth 错误(OAuthTokenError/OAuthFlowError,瞬时)→ 返回降级文案但**不**置 sticky、不崩 loop;③ 否则按断线/重连或原样抛。保留上游 `_auth_unavailable` 预检短路。

### D6. TokenStorage 用每-provider 内存实现
- **决策**:`_FleetentTokenStorage` 极简内存实现(满足 SDK Protocol)。provider 随 `_open_session_for` 每次建会话新建一次 → token 缓存在**会话存活期**内有效(SDK 存在 context),**跨 reopen 不保留**(reopen 后冷启动,多一次 reauth 往返)。判断:reopen 罕见,代价可接受,换来零新增 per-server 持久字段。

### D7. RFC 8707 资源参数会被带上 —— 接受
- **事实**:`should_include_resource_param` 在协议版本 ≥ 2025-06-18 时返回 True;fleetent 用 LATEST(2025-11-25),故 client_credentials 取 token 请求会带 `resource=<server_url>`(把 token 绑定到该资源,安全增强)。
- **决策**:接受(这正是采用 B 的收益之一)。**要求 token 端点能接受或忽略 `resource` 参数**——标准授权服务器应能容忍未知参数。

---

## 风险

### R1.(需审核)B 对"裸"自托管 MCP 服务可能直接失败
- **事实**(`_handle_protected_resource_response`,`oauth2.py:301-309`):401 后探测 `.well-known/oauth-protected-resource`,返回 **200→用、404→跳过、其它(401/403/500)→直接 raise OAuthFlowError**。
- **后果**:若 MCP 服务端对所有路径(含 .well-known)一律 401(常见的"全站鉴权"裸服务),B 会在探测处抛错、认证失败。**B 要求服务端对不存在的 .well-known 返回 404(而非 401)。**
- **缓解**:无法在不重写 auth_flow 的前提下绕开;已在 spec 与本文档显式记录为服务端合规前提。这是 B 相对 A(零服务端要求)的实质收窄。

### R2. 无真实 oauth2 服务可端到端验证
- my-bot 当前无 `auth_type: oauth2` 服务。验证靠单测 + httpx `MockTransport` 模拟完整 401→发现(404)→token POST(200)→重试(200) 序列(驱动**真实** SDK provider + 本子类),非真实服务器冒烟。

### R3. 耦合 SDK 内部(`context`、`_handle_token_response`、`oauth_metadata`)
- preseed 与 sticky 覆盖依赖 SDK 内部结构,SDK 升级(extension 较新)可能破。已有依赖护栏:迁移后跑 MCP 全套单测可即时发现签名漂移。

---

## 可回退性
- 切换点集中在 `_oauth_auth(server)` 这一个工厂函数 + 被删的 A 机器。若审核后认为 B 不合适,回退 = 还原本 change(git revert PR),A 仍在 git 历史中。
