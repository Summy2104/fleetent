# mcp-per-user-session Specification

## Purpose
TBD - created by archiving change mcp-per-user-oauth2. Update Purpose after archive.
## Requirements
### Requirement: per-user oauth 服务的会话/进程按用户隔离

对于 per-user oauth 的 MCP 服务,系统 SHALL 将会话/子进程按用户隔离:会话注册键由 `(scope, server_id)` 扩展为 `(scope, server_id, user_id)`。同一用户的多次/并发调用 MUST 复用同一会话/进程(JSON-RPC 多路复用),不同用户 MUST 各自独立。工具名投影 MUST 保持 user-agnostic(仍为 `{server_id}__{tool_name}`),用户维度仅存在于路由键,MUST NOT 进入工具名。非 per-user 服务的会话键与行为 MUST 保持不变(向后兼容)。

#### Scenario: 不同用户路由到各自会话
- **WHEN** 用户 A 与用户 B 先后调用同一 per-user oauth 服务的同一工具
- **THEN** 系统按当前 principal.user_id 路由到各自 `(scope, server_id, user_id)` 的会话/进程,各以自己的身份执行

#### Scenario: 同一用户并发调用复用同一会话
- **WHEN** 同一用户对同一服务并发发起多次工具调用
- **THEN** 复用该用户的单一会话/进程(JSON-RPC id 多路复用),不重复创建

#### Scenario: 工具名不含用户维度
- **WHEN** 模型查看/调用 per-user oauth 服务的工具
- **THEN** 工具名为 `{server_id}__{tool_name}`(不含 user),路由由 principal.user_id 在底层完成

#### Scenario: 非 per-user 服务行为不变
- **WHEN** 一个未配置 per-user oauth 的 MCP 服务被调用
- **THEN** 其会话键仍为 `(scope, server_id)`,行为与现状一致

### Requirement: streamable http 经 per-user session 与逐请求 Bearer 注入

http 传输的 per-user oauth 服务 SHALL 为每个用户开独立 ClientSession,该会话的 HTTP 客户端 SHALL 绑定一个自定义 `httpx.Auth`,其在**每个请求**的 `auth_flow` 中读取该用户当前 token 并设置 `Authorization: Bearer`。token 刷新后 MUST 对调用透明且无需重建会话(下一请求自动携带新 token)。实现 SHALL 使用未弃用的 transport API(`streamable_http_client(url, http_client=<带 auth 的 AsyncClient>)`),旧 `streamablehttp_client(headers=,auth=)` 入口保留 re-export shim。

#### Scenario: 逐请求注入当前用户 Bearer
- **WHEN** 某用户经其 per-user http 会话发起工具调用
- **THEN** 自定义 auth 在该请求读取该用户当前 token 并以 `Authorization: Bearer` 注入

#### Scenario: 刷新对会话透明不重连
- **WHEN** 该用户 token 在会话存续期间被刷新
- **THEN** 后续请求经 `auth_flow` 自动读取到新 token,无需重建 ClientSession

### Requirement: stdio per-user 子进程隔离与生命周期

对标准 env 认证的 stdio per-user oauth 服务,系统 SHALL 为每个用户 spawn 独立子进程,该用户的 token 在 spawn 时注入子进程环境。不同用户 = 不同子进程;同一用户复用其子进程。每条子进程 MUST 由唯一 owner task 持有(enter/exit 同 task),回收 MUST 经向 owner task 发信号完成,MUST NOT 跨 task 拆栈。子进程寿命 MUST NOT 超过其 token 有效期;token 过期或遇 `401` 时 SHALL 用刷新后的 token 重启子进程。系统 SHALL 对子进程做空闲超时回收,并 SHALL 施加总量上限与每用户上限(触发驱逐时 MUST 记日志,不得静默截断),agent 异常退出后 MUST 清理孤儿子进程。关停链路每步 MUST 舱壁化(独立超时,单点失败只记日志、不改进程退出码)。

#### Scenario: 不同用户 spawn 不同子进程
- **WHEN** 用户 A 与用户 B 调用同一 stdio per-user oauth 服务
- **THEN** 各自 spawn 独立子进程,A 的 token 注入 A 的进程 env、B 的注入 B 的进程 env

#### Scenario: 同一用户复用子进程
- **WHEN** 同一用户对该服务发起后续调用且其子进程仍存活
- **THEN** 复用该子进程,不重新 spawn

#### Scenario: token 过期重启子进程
- **WHEN** 某用户子进程的 token 过期或调用遇 `401`
- **THEN** 系统以刷新后的 token 重启该用户子进程后重试,调用方拿到正常结果

#### Scenario: 空闲超时回收经 owner task 信号
- **WHEN** 某用户子进程空闲超过配置阈值
- **THEN** 回收器向该子进程的 owner task 发信号、由其自身收尾关闭(不跨 task 拆栈)

#### Scenario: 达上限时驱逐并记日志
- **WHEN** 子进程总量或某用户子进程数达到上限,需为新用户/新服务腾出
- **THEN** 系统按策略驱逐(如最久未用)并记录日志,不静默丢弃

#### Scenario: 关停舱壁化优雅退出
- **WHEN** agent 优雅关停,需收尾所有 per-user 子进程
- **THEN** 每条子进程独立超时收尾,单条失败只记日志、不波及其它、不改变优雅路径的退出码

