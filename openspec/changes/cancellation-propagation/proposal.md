## Why

主循环（`agent_loop.run()` / `run_stream()`）当前无法被外部取消：一旦任务进入「调 LLM → 调度工具 → 再调 LLM」的循环，外部（用户点取消、HTTP 连接断开、上层超时）没有任何手段让它真正停下来。即便上层 `asyncio.Task` 被 cancel，正在执行的工具——尤其是 `run_code` 拉起的 Docker 沙箱容器、未来的 MCP 长连接——也不会被主动中止与清理，导致容器/连接泄漏、资源占用。

这是 AR19（取消与超时传播）。它建立一条**单向的取消信号通路**（cancel token）贯穿主循环和每一次工具调用，并提供**两层保护**：cooperative（协作式）——主循环在每个检查点查询 token，已取消则以 `cancelled` 原因码（AR1 已预留）优雅停止；硬 deadline——为正在进行的工具执行设定真正的中止动作，使沙箱容器、MCP 连接被实际终止并释放资源，而非仅停止等待。

> 本 change 是波次 3 的**接口地基**：cancel token 的接口契约会被后续超时类功能复用——T2（工具超时保护）、SB7（沙箱超时）都将以「构造一个带 deadline 的 cancel token 传入工具执行」的方式接入。因此本 change 的首要目标是把 token 的接口定准、对外发布为契约（见 design D1）。

## What Changes

- 新增**取消传播原语**（建议 `src/fleetent/cancellation.py`）：定义一个 `CancelToken`（协作式取消信号）数据结构与查询/触发接口，作为单向信号在主循环与工具调用间传递。
- 主循环在每个终止检查点查询 token：已取消 → 以 `cancelled` 原因码（AR1 预留）优雅停止，复用 AR1 终止框架（注册一个 `CancellationChecker`，**不改循环体判定分支**）。
- cancel token 单向流入工具调度（`_safe_dispatch` → `dispatch`）：接受 token 的工具（首先是 `run_code` / 沙箱）在执行中观察 token，被取消时**真正中止底层资源**——`SandboxClient` 强制销毁容器（`docker rm -f`），不只是停止 `await`。
- 两层语义明确：cooperative（主循环检查点 + 工具协作查询）+ 硬 deadline（token 可携带绝对截止时间，到点等同已取消，用于硬性兜底）。
- 外部取消入口：`run()` / `run_stream()` 接受一个可选 `cancel_token` 参数；不传时构造一个永不取消的默认 token，使现有调用方行为字节级不变。
- `cancelled` 终止时原因码写入 trace（复用 AR1 的 `stop_reason` 出口），并记录取消发生的时点信息。

## Capabilities

### New Capabilities
- `agent-cancellation-propagation`: 贯穿主循环与所有工具调用的单向 cancel token 通路，两层保护（cooperative 检查点 + 硬 deadline）。外部取消到达时主循环以 `cancelled` 原因码优雅停止，正在进行的工具执行（沙箱容器、MCP 连接）被真正中止并释放资源；cancel token 接口对外发布为波次 3 超时类功能（T2 / SB7）依赖的契约。本 capability 同时新增一条「`cancelled` 终止已接入主循环」需求：AR1 spec 把 `cancelled` 列为「已定义但无 checker、永不触发」的预留原因码，本 change 注册 `CancellationChecker` 后该原因码成为可触发终止原因——该接入需求归本 change 自己的新 capability（ADDED），不 MODIFY `agent-loop-termination`，避免与并行 change（循环检测 / 迭代预算）就同一条注册表需求互相覆盖。

### Modified Capabilities
- `sandbox-client`: `SandboxClient` 需新增「提供幂等的强制销毁（`destroy_workspace` 重复调用不抛）以承接取消/超时的硬中止语义」的可观察行为；硬中止的编排由 `run_code` 负责（见 design D3），`SandboxClient` 仅保证销毁幂等；既有 create/exec/destroy 的正常路径行为不变。
<!-- 不 MODIFY agent-loop-termination：AR1 spec「预留原因码尚未激活」的表述由本 change 自带的「cancelled 终止已接入主循环」ADDED 需求超越；与并行 change 各自 ADD、互不冲突。归档顺序见 design ## Context。 -->


## Impact

- **代码**：
  - 新增 `src/fleetent/cancellation.py`（`CancelToken` 数据结构 + `is_cancelled()` / `cancel()` / 携带 `deadline` 的查询 + 默认永不取消的 token 构造）。**此模块定义对外契约**（见 design D1）。
  - 修改 `src/fleetent/termination.py`：在 `LoopState` 上承载对 `CancelToken` 的引用（或由 checker 直接持有 token）；`cancelled` 原因码已存在，无需新增枚举。新增 `CancellationChecker`（可放本模块或 cancellation.py）。
  - 修改 `src/fleetent/agent_loop.py`：`run()` / `run_stream()` 新增 `cancel_token: CancelToken | None = None` 参数；`_build_controller` 注册 `CancellationChecker`；工具调度路径把 token 透传给 `_safe_dispatch`。
  - 修改 `src/fleetent/tool_registry.py`：`dispatch` 把 token 作为**带外 kwarg** 透传给声明接受 token 的工具（opt-in，按注册标记/参数名约定识别）；并修改 `_build_schema`（行 84-101）使其**排除**该 token 参数——否则 `_build_schema` 会把无默认值的 `cancel_token` 形参当作 string 必填字段暴露给 LLM。不接受 token 的工具签名与 schema 不变。
  - 修改 `src/fleetent/tools.py` 的 `run_code` + `src/fleetent/sandbox_client.py`：`run_code` 持有容器 `ws_id`（`SandboxClient` 实例不持有），由 `run_code` 用 asyncio 编排「`exec` 任务 + token 观察任务」，取消时调 `client.destroy_workspace(ws_id)` 强制 `docker rm -f` 并中止等待；`SandboxClient` 仅提供幂等的 `destroy_workspace`（重复销毁不抛）。
- **配置**：本 change 不新增部署级配置（硬 deadline 的具体时长由调用方/波次 3 的超时功能设定；本 change 只提供 token 携带 deadline 的能力）。
- **测试**：新增 `tests/test_cancellation.py`（token 协作语义、deadline 等同取消、默认永不取消）；`tests/test_agent_loop.py` 补充「取消后主循环以 `cancelled` 优雅停止、不再调 LLM」；`tests/test_sandbox_client.py` 补充「取消时容器被强制销毁」（mock docker 子进程，不发真实请求）。LLM 调用按规范 mock。
- **不影响**：不传 `cancel_token` 时所有现有调用方行为字节级不变；model fallback、错误分类、permission_gate、上下文压缩、`max_turns` / `consecutive_failures` 判定不变；不引入新依赖。
