## Context

apply `tui-gateway` 时发现:`run_stream`(流式路径)设 `include_approval=False`,不调用 `permission_gate`,因此既有 SSE `/chat` 和新 TUI 网关在流式中都不门控 medium/high 工具,也无法产生 `approval_required`。非流式 `run()` 才门控(`include_approval=True`,在 `_dispatch_*` 中 `await _default_gate.request_approval`,拒绝置 `LoopState.approval_rejected`)。`tui-gateway` 已实现 `approve`(resolve)与 `approval_required` 渲染,只差一个事件源。

## Goals / Non-Goals

**Goals:**
- 让流式路径**可选**门控审批,并在阻塞前把 `approval_required` 作为流事件吐给消费者。
- 与非流式 `run()` 的放行/拒绝语义对齐(拒绝→既有 `approval_rejected` 终止)。
- 点亮 `tui-gateway` 已实现的审批 UI;全程可单测、不发真实 LLM。

**Non-Goals:**
- 不默认开启(保护 SSE `/chat` 单向通道——开了会在途阻塞且无法在同通道审批)。
- 不改 `run()`、`permission_gate`、工具注册/访问控制的契约。
- 不在本 change 重写 message_hygiene/批次保序(复用既有)。

## Decisions

### D1 — opt-in 参数 `stream_approvals`,默认 False
`run_stream(..., stream_approvals: bool = False)`。仅当 True 时把内部 `include_approval` 置 True 并启用“先发事件再等待”的流式审批分支。默认 False ⇒ run_stream 行为逐字节不变(SSE `/chat` 与所有现有调用不受影响)。**只有 `tui-gateway` 的 `dispatch.send` 传 True**(双向通道才有意义)。

### D2 — `approval_required` 必须在阻塞**之前**进入事件流
关键时序:消费者要先看到 `approval_required` 才能 `approve`;若先 `await request_approval` 再 yield,客户端在看到提示前就被阻塞、死锁。机制:流式 dispatch 在调用 `request_approval` 之前,先把 `approval_required{approval_id, tool, risk, args}` 事件 emit 到 run_stream 的产出流(经现有的事件 yield 通道),然后再 `await` 审批;审批返回后继续(批准→工具入批;拒绝→`approval_rejected`)。需要复用 `run()` 串行审批的 D3 次序(逐工具、原序、只有批准的进并行批)。

### D3 — 拒绝复用 `approval_rejected`(AR1)
拒绝时置 `LoopState.approval_rejected`、写占位 tool_result 保消息契约,在下一个 while-top 由既有 `ApprovalRejectedChecker` 终止(方案 A)。本 change 把 AR1 的 `approval_rejected` 从“仅 run() 生效”扩展到“stream_approvals=True 的流式路径也生效”——是对既有终止框架的复用,不新增 StopReason。

### D4 — 与 tui-gateway 的边界
网关 `dispatch._stream_run` 已把 run_stream 每个事件透传为 `event` 通知,`render.render_event` 已处理 `approval_required`,`approve` 方法已转 `permission_gate.resolve`。故本 change 几乎全在 `agent_loop`;tui 侧仅 `dispatch.send` 多传 `stream_approvals=True`。审批 `approval_id` 即 `permission_gate` 生成的 id,`approve` 用同一 id resolve,天然闭环。

### D5 — 测试策略(TDD,全 mock)
- agent_loop:mock `_default_gate.request_approval`(返回 approved/rejected),mock LLM 产出一个需审批工具调用;断言 `stream_approvals=True` 时事件序列里 `approval_required` 出现在审批等待之前、批准→工具执行事件、拒绝→流式终止;`stream_approvals=False`(默认)时无 `approval_required`、不调用 gate(回归保护)。
- tui:dispatch.send 传 True 时,gateway 把 `approval_required` 透传为 event 通知(用既有 FakeTransport + mock run_stream 注入该事件)。

## Risks / Trade-offs

- [流式中阻塞等待审批] → 仅 opt-in;双向 WS 客户端能在同通道 `approve` 解阻塞;SSE 默认不开。
- [改 run_stream 签名] → 加默认值参数,向后兼容;默认路径行为不变,有回归测试守。
- [事件时序/死锁] → D2 明确“先 emit 再 await”;测试覆盖顺序。
- [与既有 AR3/message_hygiene 的批次保序交互] → 复用 run() 已验证的串行审批+批次逻辑,不重写。

## Open Questions

- 是否给 SSE `/chat` 也加一个 opt-in query/header 开关?**v1 不做**(SSE 单向,审批无法在途回传);留待有需求再议。
- `approval_required` 是否带工具 `args` 全量还是摘要?倾向摘要/截断(与 render 截断一致),**实施时定**。
