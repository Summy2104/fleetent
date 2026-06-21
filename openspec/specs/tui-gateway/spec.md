# tui-gateway Specification

## Purpose
TBD - created by archiving change tui-gateway. Update Purpose after archive.
## Requirements
### Requirement: WebSocket 网关端点

系统 SHALL 暴露一个 WebSocket 端点 `/ws`,在其上承载 newline-delimited JSON-RPC 2.0 双向协议。系统 SHALL 在接受连接后立即向客户端发送一条 `gateway.ready` 事件通知。现有 SSE `/chat` 端点 SHALL 保持不变并继续可用。

#### Scenario: 连接建立后收到 ready
- **WHEN** 客户端成功建立 `/ws` WebSocket 连接并通过认证
- **THEN** 系统发送一条 `method: "event"`、`params.type: "gateway.ready"` 的 JSON-RPC 通知

#### Scenario: SSE 端点不受影响
- **WHEN** 引入 `/ws` 后客户端调用既有 `POST /chat`
- **THEN** SSE 行为与引入前一致

#### Scenario: 非法 JSON 帧
- **WHEN** 客户端发送一行非合法 JSON
- **THEN** 系统回送 JSON-RPC 错误 `code: -32700`(parse error)且不关闭连接

### Requirement: 连接认证

系统 SHALL 校验 WebSocket 连接的 Bearer `ma-` key,认证失败 SHALL 关闭连接。通过认证的连接 SHALL 绑定到对应内部 user,后续请求在该 user 作用域内执行。

#### Scenario: 有效 key 通过
- **WHEN** 客户端以有效 `Authorization: Bearer ma-<hex>` 建立连接
- **THEN** 连接被接受,且绑定到该 key 对应的 user

#### Scenario: 无效 key 拒绝
- **WHEN** 客户端以缺失或无效的 key 建立连接
- **THEN** 系统关闭连接且不进入消息循环

### Requirement: send 方法触发流式 run

系统 SHALL 支持 `send` 请求 `{message, session_id?}`,触发一次 agent run,并将 `run_stream` 产出的事件逐条映射为 `event` 通知推送给客户端,顺序与产出顺序一致。`send` 的 JSON-RPC 响应 SHALL 包含本次运行的 `run_id`。

#### Scenario: 发送消息得到流式事件
- **WHEN** 客户端发送 `send{message:"hi"}`
- **THEN** 系统返回含 `run_id` 的响应,并随后按序推送 `text_delta`/`tool_call`/`tool_result`/`done` 等 `event` 通知

#### Scenario: 事件映射保序
- **WHEN** `run_stream` 依次产出 `tool_call` 再 `tool_result` 再 `done`
- **THEN** 客户端收到的 `event` 通知顺序与之一致

#### Scenario: run 内错误
- **WHEN** `run_stream` 产出 `error` 事件
- **THEN** 系统推送 `params.type: "error"` 的 `event` 通知,连接保持可用

### Requirement: abort 方法中断运行

系统 SHALL 支持 `abort` 请求 `{run_id}`,通过该 run 的 `CancelToken` 中断在途运行。中断后系统 SHALL 推送一条收口通知(`done` 或 `error`,标识 aborted),不得泄漏未配对的 tool 事件。

#### Scenario: 中断在途 run
- **WHEN** 某 run 正在产生事件,客户端发送 `abort{run_id}`
- **THEN** 该 run 的 CancelToken 被取消,系统停止推送该 run 的后续工具事件并推送一条收口通知

#### Scenario: abort 未知 run_id
- **WHEN** 客户端 abort 一个不存在或已结束的 run_id
- **THEN** 系统返回 `{ok:false}` 或 `{aborted:false}` 且不崩连接

### Requirement: 审批解决经 WebSocket 暴露

系统 SHALL 支持 `approve` 请求 `{approval_id, decision}`,将决定(`approved`/`rejected`)转交既有 `permission_gate` 解析,复用既有审批机制、不改变其行为。这是又一个审批解决入口,与既有 `POST /approvals/{id}/resolve` 等价。

> **v1 范围说明**:`run_stream`(流式路径)当前不做审批门控(`include_approval=False`),因此流式过程中**不会**产生 `approval_required`,系统在 v1 **不**主动推送该事件。让流式路径门控并发出 `approval_required` 是一个独立的 agent-runtime 变更(`streaming-approval-gating`),落地后客户端的审批渲染再启用。本能力先保证“解决”可用。

#### Scenario: 批准放行
- **WHEN** 客户端发送 `approve{approval_id, decision:"approved"}`
- **THEN** 系统调用 permission_gate 解析为通过,返回 `{ok:true}`(该 approval 存在时)

#### Scenario: 拒绝
- **WHEN** 客户端发送 `approve{approval_id, decision:"rejected"}`
- **THEN** 系统将该审批解析为拒绝

#### Scenario: 非法 decision
- **WHEN** 客户端发送的 `decision` 不是 `approved`/`rejected`
- **THEN** 系统回送 JSON-RPC 错误 `code: -32602`(invalid params)

### Requirement: 会话方法

系统 SHALL 支持 `session.new` 创建新会话并返回 `session_id`,以及 `session.list` 返回当前 user 名下的会话列表。会话访问 SHALL 经既有 session 管理层,保持其 per-session 锁语义不变。

#### Scenario: 新建会话
- **WHEN** 客户端发送 `session.new`
- **THEN** 系统返回一个新的 `session_id`,后续 `send` 默认作用于该会话

#### Scenario: 列出会话仅限本 user
- **WHEN** 客户端发送 `session.list`
- **THEN** 返回的会话仅包含该连接所绑定 user 的会话

### Requirement: Transport 抽象与 peer-gone 语义

系统 SHALL 通过一个 Transport 抽象(`write(obj) -> bool`、`close()`)发送帧,由单一 dispatch 处理所有方法。Transport SHALL 在客户端断开(peer-gone)时令写操作返回失败信号并触发连接清理,而对真实 I/O 错误重新抛出以便记录,不得将真实错误伪装成干净断开。

#### Scenario: 客户端断开触发清理
- **WHEN** 写帧时检测到 WebSocket 已断开
- **THEN** 系统标记该 transport 失效,取消该连接所有在途 run,并解绑其会话

#### Scenario: 真实错误不被吞
- **WHEN** 发送帧时发生非断开类的真实错误
- **THEN** 错误被抛出/记录,而非当作干净断开静默处理

### Requirement: 终端 TUI 客户端

系统 SHALL 提供一个纯 Python 终端客户端(入口 `fleetent chat` 子命令),连接 `/ws`,消费 `event` 通知做增量渲染:流式文本、工具调用展示、状态/spinner。客户端 SHALL 提供多行输入与斜杠命令(`/new`、`/session`、`/abort`、`/approve`、`/quit`、`/help`),并使输入行与流式输出在同一终端共存而不互相破坏。流式输出 SHALL **持久显示**:输出在运行中的输入行**上方**提交,不得被 prompt 的下一次重绘擦除("一闪而过");为此客户端 SHALL 仅以**完整行**(以换行结尾)输出流式文本——半行(无换行)文本在 prompt 上方不会被提交到终端 scrollback、会被重绘擦掉。结构化事件之间 SHALL NOT 产生多余空行。客户端 SHALL 支持通过 `--url`/`--token` 指定服务端地址与认证。不得引入 Node 或前端构建链。

#### Scenario: 流式文本持久显示
- **WHEN** 客户端收到一串 `text_delta` 事件
- **THEN** 对应文本在输入行上方显示,且在后续 prompt 重绘后**仍然可见**(不被擦除)
- **AND** 输入行保持可编辑、不被打断破坏

#### Scenario: 事件之间不堆多余空行
- **WHEN** 客户端连续收到结构化事件(如 `tool_call` 紧跟 `tool_result`),或在文本之后收到结构化事件
- **THEN** 各事件各占其行,相邻事件之间不出现由渲染产生的空行(agent 自身内容里的空行除外)

#### Scenario: 斜杠命令中断
- **WHEN** 用户在运行中输入 `/abort`(或按 Ctrl-C)
- **THEN** 客户端向服务端发送 `abort` 请求中断当前 run

#### Scenario: 审批决定
- **WHEN** 用户用 `/approve <approval_id> <approved|rejected>` 作出决定
- **THEN** 客户端发送 `approve` 请求并将决定回传服务端
- **NOTE** v1 不会收到 `approval_required` 推送(流式路径不门控,见上文范围说明);客户端的 `approval_required` 渲染待 `streaming-approval-gating` 落地后启用

#### Scenario: 工具调用展示
- **WHEN** 客户端收到 `tool_call`/`tool_result` 事件
- **THEN** 终端以可辨识的方式展示工具名与(截断的)结果

#### Scenario: 入口经 fleetent chat 子命令
- **WHEN** 用户启动终端客户端
- **THEN** 经 `fleetent chat`(而非已改名的旧 `tui` 子命令或已移除的独立 `fleetent-tui` console-script)

### Requirement: 客户端断连处理

客户端 SHALL 在连接失败或中断时显示状态并按退避策略尝试重连,启动与请求 SHALL 受可配置超时约束。

#### Scenario: 断线重连
- **WHEN** 与服务端的连接意外中断
- **THEN** 客户端显示断开状态并按退避重连,而非静默挂起或崩溃

#### Scenario: 连接超时
- **WHEN** 在配置的超时内未能建立连接
- **THEN** 客户端报告超时错误并退出或重试

