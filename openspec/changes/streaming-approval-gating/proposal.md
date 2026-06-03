## Why

`run_stream()` 设 `include_approval=False`——**流式路径对 medium/high 风险工具不做审批门控**(SSE `/chat` 与新的 TUI WebSocket 网关都走 run_stream)。`tui-gateway` 的双向 WS 本可在同一通道承载审批交互(服务端推 `approval_required`、客户端 `approve` 回传),但因 run_stream 从不产生 `approval_required`,`tui-gateway` v1 只能“解决(resolve)”审批、无法在流式中“发起(surface)”。

本 change 给流式路径加 **opt-in** 审批门控 + `approval_required` 事件,点亮 TUI 已实现的审批渲染,同时保持 SSE `/chat` 现状不变。

## What Changes

- **`run_stream` 新增 opt-in 流式审批门控**(参数 `stream_approvals: bool = False`,默认关):开启时,medium/high 工具进入审批等待**之前**先 yield 一个 `approval_required` 事件(`{approval_id, tool, risk, args}`),再 `await permission_gate.request_approval`,按结果放行/拒绝(拒绝复用既有 `approval_rejected` 终止,AR1)。默认关闭时流式路径行为与现状完全一致。
- **`tui-gateway` 的 `dispatch.send` 开启 `stream_approvals=True`**:网关已把 run_stream 事件透传为 `event` 通知、TUI `render` 已能渲染 `approval_required`(`tui-gateway` 已实现),故本 change 落地后客户端审批渲染自动点亮。
- **不改**非流式 `run()` 的审批行为;**不默认门控** SSE `/chat`(opt-in,单向通道无法在途审批,继续用 `/approvals` 旁路)。

## Capabilities

### New Capabilities
- `streaming-approval-gating`: run_stream 上的 opt-in 审批门控契约——开启时在审批阻塞前先发 `approval_required` 流事件、再等待 `permission_gate` 决定,放行/拒绝语义与非流式 `run()` 对齐;默认关闭时不改变既有流式行为。

### Modified Capabilities
<!-- 无:opt-in 参数,默认值保持 run_stream 现有契约不变;permission_gate 行为仅被复用。 -->

## Impact

- **代码**:`agent_loop.py`(run_stream + 共享流式 dispatch:`include_approval` 由参数驱动;审批阻塞前把 `approval_required` 吐进事件流);`src/fleetent/tui/dispatch.py`(`send` 传 `stream_approvals=True`)。
- **复用,不改契约**:`permission_gate`(request_approval/resolve)、`tui-gateway` 的事件透传与 render。
- **不受影响**:SSE `/chat`(默认不门控)、非流式 `run()`、工具注册/访问控制。
- **依赖前置**:`tui-gateway`(已实现 approve 解决 + approval_required 渲染)、`agent-loop-termination`(AR1 的 `approval_rejected`)。
- **分支**:基于并合回 `main`。
