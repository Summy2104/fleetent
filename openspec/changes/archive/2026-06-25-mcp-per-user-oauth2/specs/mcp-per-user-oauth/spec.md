## ADDED Requirements

### Requirement: 缺失 per-user token 时触发授权而非失败

当一个配置为 per-user OAuth(authorization_code)的 MCP 服务被某用户调用、而该 `(user, agent, server)` 尚无有效 token 时,系统 SHALL 不抛异常、不卡住,而 MUST 返回一个明确的「需授权」结果(挂在既有 degradation/降级链上),并 SHALL 触发向该用户投递授权链接的流程。已有有效 token 的调用 MUST 正常执行,不触发授权。

#### Scenario: 无 token 的用户调用触发需授权结果
- **WHEN** 用户对一个 per-user oauth 的 MCP 服务发起工具调用,且其 `(user, agent, server)` 无有效 token
- **THEN** 调用返回明确的「需授权」结果(不抛异常、不卡住),并触发向该用户投递授权链接

#### Scenario: 已授权用户的调用正常执行
- **WHEN** 用户对同一服务发起调用,且其 `(user, agent, server)` 已有未过期 token
- **THEN** 调用以该用户身份正常执行,不触发授权流程

### Requirement: 授权链接采用 Authorization Code + PKCE 且 state 绑定 user×agent×server

系统 SHALL 生成 OAuth 2.1 Authorization Code 授权链接,MUST 包含 PKCE `code_challenge`(method S256)与 `state`。`state` MUST 绑定到发起授权的 `(user_id, agent_id, server_id)`,MUST 不可猜测、一次性消费且具备短 TTL;`redirect_uri` MUST 与授权服务器预注册值精确匹配。回调以 `state` 反查发起者身份,MUST NOT 依赖回调请求中的登录态。

#### Scenario: 生成带 PKCE 与绑定 state 的授权链接
- **WHEN** 为某 `(user, agent, server)` 生成授权链接
- **THEN** 链接含 `response_type=code`、`code_challenge`(S256)、`state`,且 `state` 在服务端映射到该 `(user_id, agent_id, server_id)` 与对应的 PKCE verifier

#### Scenario: 回调以 state 反查身份完成 code 交换
- **WHEN** 用户在浏览器完成授权,授权服务器重定向回 `redirect_uri` 带回 `code` 与 `state`
- **THEN** 系统校验 `state`(存在、未过期、未被消费)→ 反查出 `(user, agent, server)` 与 PKCE verifier → 以 `code`+verifier 向 token 端点交换 access+refresh token 并入库;`state` 随即作废

#### Scenario: 非法或过期 state 被拒绝
- **WHEN** 回调携带的 `state` 不存在、已过期或已被消费
- **THEN** 系统拒绝该回调、不交换 token、不写入任何 token

### Requirement: token 按 user×agent×server 隔离

per-user token 的存储与查取 SHALL 以 `(user_id, agent_id, server_id)` 三元组为键。一个 agent 下某用户的授权 MUST NOT 被另一个 agent 使用;同一用户对不同 agent MUST 分别授权。token 解析 MUST 使用当前调用消息的发送者身份(principal.user_id),MUST NOT 以会话/频道/对话为授权归属。

#### Scenario: agent1 的授权不可用于 agent2
- **WHEN** 用户在 agent1 下完成对某 server 的授权,随后在 agent2 下调用同一 server
- **THEN** agent2 查 `(user, agent2, server)` 无 token → 触发 agent2 自己的授权流程,绝不复用 agent1 的 token

#### Scenario: 共享频道中按发送者隔离
- **WHEN** 用户 B 在用户 A 开启的会话/消息列中发消息并触发该 server 的工具调用
- **THEN** token 按 B 的 `user_id` 解析(B 无 token 则 B 被要求自己授权),绝不复用 A 的 token

### Requirement: per-user token 解析经可注入缝

MCP client SHALL 暴露一个模块级可注入的 per-user token resolver 缝(如 `set_user_token_resolver`),签名按 `(server_id, user_id[, agent_id]) -> token | None`。未注入时(standalone 默认)SHALL 回退到本地实现;注入后(managed)SHALL 经注入实现取 token。该缝 MUST NOT 引入 agent runtime 对 platform 的反向 import,MUST NOT 以模块级可变全局持有活资源。

#### Scenario: 未注入时回退本地实现
- **WHEN** 运行于 standalone(未调用 `set_user_token_resolver`)
- **THEN** MCP client 经本地实现解析 per-user token,不依赖任何 platform 组件

#### Scenario: 注入后经注入实现取 token
- **WHEN** 调用 `set_user_token_resolver(resolver)` 注入实现后发起需 token 的调用
- **THEN** MCP client 经该注入 resolver 取 token

### Requirement: standalone 自托管授权流程与本地加密 token 存储

在 standalone 部署(无 platform)下,agent SHALL 自挂 OAuth 回调端点(如 `GET /oauth/callback`)完成 code 交换;per-user token SHALL 加密存于 agent 侧本地库(经嵌入式 forward-only 迁移建表),按 `(user_id, agent_id, server_id)` 隔离;access token 过期时 agent SHALL 用 refresh token 自行刷新;授权链接 SHALL 经 agent 自身的 IM 连接器投递给该用户本人。改动后 agent MUST 仍能在无 platform、platform 表不存在的环境下完成 `fleetent agent run` 对话(无 per-user oauth 配置的服务行为不变)。

#### Scenario: standalone 下完成授权并以用户身份调用
- **WHEN** standalone 部署中,用户首次调用 per-user oauth 服务 → 收到授权链接 → 浏览器授权 → 回调命中 agent 自挂的 `/oauth/callback`
- **THEN** agent 交换并加密存储该用户 token,后续该用户调用以其身份执行

#### Scenario: standalone 下 access token 过期自行刷新
- **WHEN** standalone 中某用户的 access token 过期且本地持有有效 refresh token
- **THEN** agent 用 refresh token 自行刷新并继续调用,对调用方透明

#### Scenario: 无 platform 环境下基础对话不受影响
- **WHEN** 在无 platform、platform 表不存在的环境运行 `fleetent agent run`
- **THEN** 基础对话与无 per-user oauth 配置的 MCP 服务行为不变
