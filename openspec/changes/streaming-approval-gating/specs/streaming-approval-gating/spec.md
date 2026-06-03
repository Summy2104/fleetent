## ADDED Requirements

### Requirement: run_stream 的 opt-in 审批门控

`run_stream` SHALL 接受一个 `stream_approvals` 开关(默认关闭)。当且仅当开启时,流式路径 SHALL 对 medium/high 风险工具进行审批门控:在调用 `permission_gate` 等待之前,先向产出事件流发送一条 `approval_required` 事件(含 `approval_id`、工具名、风险级别、参数),随后等待审批结果。默认关闭时,`run_stream` 的行为 SHALL 与未引入本能力前完全一致(不门控、不产生 `approval_required`、不调用 `permission_gate`)。

#### Scenario: 开启时先推 approval_required 再等待
- **WHEN** `stream_approvals=True` 且 agent 调用一个需审批的工具
- **THEN** 系统先在事件流中产出 `approval_required`(含 `approval_id`),然后才进入审批等待

#### Scenario: 批准放行
- **WHEN** 该审批被解析为 `approved`
- **THEN** 被审批工具继续执行,其 `tool_call`/`tool_result` 事件正常产出

#### Scenario: 拒绝终止
- **WHEN** 该审批被解析为 `rejected`
- **THEN** 系统按既有 `approval_rejected` 终止该 run(写占位 tool_result 保消息契约),不再继续后续轮次

#### Scenario: 默认关闭不门控(回归保护)
- **WHEN** `stream_approvals` 未开启(默认)
- **THEN** 流式路径不调用 `permission_gate`、不产出 `approval_required`,行为与现状一致

### Requirement: TUI 网关启用流式审批

`tui-gateway` 的 `send` SHALL 以 `stream_approvals=True` 驱动 run_stream,使 `approval_required` 事件经既有事件透传到达客户端;客户端 SHALL 据此渲染审批提示,并以既有 `approve` 请求解决之。复用既有网关事件透传与 `permission_gate`,不改其契约。

#### Scenario: 网关透传 approval_required
- **WHEN** 经 WS `send` 触发的 run 命中一个需审批的工具
- **THEN** 客户端收到 `params.type: "approval_required"` 的 `event` 通知,并可用 `approve` 回传决定
