## Context

`agent_loop.run()`（行 234）与 `run_stream()`（行 425）的主循环没有任何取消入口。工具调度走 `_safe_dispatch`（行 62）→ `tool_registry.dispatch`（行 61）；`run_code`（tools.py 行 50）通过 `SandboxClient` 拉起 Docker 容器：`create_workspace`（`docker run -d`）→ `exec`（`docker exec` + `proc.communicate()`）→ `finally: destroy_workspace`（`docker rm -f`）。当上层 `asyncio.Task` 被 cancel 时，正在 `await proc.communicate()` 的 `exec` 不会主动中止容器；只有正常路径的 `finally` 才清理——若取消发生在 `communicate()` 阻塞期间，容器可能悬挂。

AR1 终止框架（已合入 `termination.py`）已把 `cancelled` 列为预留 `StopReason`，并提供「注册 checker 即接入、不改循环体」的扩展点。本 change 为 `cancelled` 补 checker，并在此之上铺一条贯穿工具层的取消信号通路。

本 change 是波次 3 的接口地基：T2（工具超时）与 SB7（沙箱超时）将复用同一 cancel token——它们的「超时」本质就是「构造一个带 deadline 的 token 传入工具执行，到点 token 视为已取消」。因此 token 的接口必须先定准并对外发布。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM；禁止全局可变状态（token 是 per-run 显式传递的对象，不用模块级可变量）；不吞异常（取消相关异常要么转为 `cancelled` 终止、要么 re-raise，不静默）；新模块结构为 import → 常量 → 数据类 → 函数；mypy strict；行长 100；TDD Hard Gate；测试 mock LLM 与 docker 子进程。

**与并行 change 的关系（归档顺序 / spec 协调）**：AR19（本 change）、AR4（循环检测）、AR2（迭代预算）同属波次 2 Track A，都依赖 AR1 终止框架（`termination.py` 已合入），且都要把 AR1 spec 中各自对应的预留原因码（`cancelled` / `loop_detected` / `budget_exceeded`）从「已定义但永不触发」激活为「已接入可触发」。为避免三者 MODIFY `agent-loop-termination` 的同一条「可扩展的终止策略注册表」需求互相覆盖、归档顺序敏感，**本 change 不 MODIFY `agent-loop-termination`**，而在自己的新 capability（`agent-cancellation-propagation`）里 ADD 一条「`cancelled` 终止已接入主循环」需求。AR1 spec 中「预留原因码尚未激活」的表述由本 change 起被本条 ADDED 需求超越；三个 change 各自独立 ADD，互不引用、无归档冲突，归档顺序可任意。本 change 另 MODIFY 真实存在、单一归属的 `sandbox-client`（幂等销毁），与上述无关。依赖上仅要求 AR1 已先行合入（已满足）。

## Goals / Non-Goals

**Goals:**
- 定义 `CancelToken` 原语：协作式取消信号 + 可选硬 deadline，单向从主循环流入工具调用。
- 主循环在每个终止检查点查询 token，已取消（或超 deadline）则以 `cancelled` 原因码优雅停止；实现为注册进 AR1 的 `CancellationChecker`。
- token 流入工具调度，接受 token 的工具（首先是沙箱）在取消时**真正中止底层资源**（强制销毁容器），而非仅停止等待。
- `cancelled` 终止写入 trace，含取消时点信息。
- 把 cancel token 的接口**对外发布为波次 3（T2 / SB7）依赖的契约**。
- 不传 token 时所有现有调用方行为字节级不变。

**Non-Goals:**
- 不实现具体的超时时长策略（T2 工具超时、SB7 沙箱超时各自的默认时长与配置项是波次 3 各自的 change）——本 change 只提供 token 携带 deadline 的能力与硬中止机制。
- 不改造 MCP 连接的取消（本 change 在沙箱上落实硬中止；MCP 的取消接入随波次 3 MCP 相关功能复用同一 token 接口，本 change 仅在 design 中标注契约，不实现 MCP 侧动作）。
- 不改 `max_turns` / `consecutive_failures` / `approval_rejected` 判定。
- 不引入新依赖、不新增部署级配置。

## Decisions

### D1：CancelToken 接口契约（对外发布，波次 3 依赖）
新增 `src/fleetent/cancellation.py`：

- `CancelToken` 数据结构，携带：取消标志 + 可选绝对截止时间 `deadline`（基于 `time.monotonic()` 的单调时钟，避免系统时钟回拨影响）。
- 查询接口 `is_cancelled() -> bool`：已被显式取消 **或** 已超过 `deadline` 时返回 True（deadline 等同取消，统一一个查询出口）。
- 触发接口 `cancel() -> None`：幂等地把 token 置为已取消（外部取消入口调用）。
- 构造接口：`CancelToken()`（永不取消、无 deadline，作默认值）；`CancelToken(deadline=...)`（带硬截止）。

**对外契约（本节为波次 3 锁定）**：工具若希望支持取消/超时，其执行体接受一个 `CancelToken` 并在阻塞点周期性查询 `is_cancelled()`；超时类功能（T2 / SB7）通过 `CancelToken(deadline=now+timeout)` 复用本接口，无需新增并行机制。`dispatch` 对「声明接受 token」的工具注入 token，对未声明的工具签名不变。

**为何**：把「取消」与「超时」统一到同一个 token 抽象下，避免波次 3 再造一套超时机制；单调时钟避免时钟回拨误判；`is_cancelled()` 合并「显式取消」与「超 deadline」让消费方只查一个出口。
**Alternatives**：①直接用 `asyncio.CancelledError` / Task.cancel——被否，`CancelledError` 无法携带「为何取消/截止时间」语义，且工具能否被 cancel 安全中止依赖实现细节，难以在工具层做确定性资源清理；②为超时单列一套 deadline 机制——被否，与取消重复，违反「波次 3 复用同一契约」目标。

### D2：CancellationChecker 注册进 AR1 框架
新增 `CancellationChecker(token)`，实现 `TerminationChecker`：`check()` 在 `token.is_cancelled()` 时返回 `StopReason.cancelled`，否则 None。`_build_controller` 注册它。主循环每轮检查点（`controller.should_stop(state)`，行 290 / 487）即自然查询到取消。

**为何**：沿用 AR1「新增终止原因 = 新增 checker」契约，主循环检查点已是每轮第一步，取消能在「下一次 LLM 调用前」被捕获，实现 cooperative 协作停止，零额外检查点。
**Alternatives**：在循环体内散插 `if token.is_cancelled()`——被否，违反 AR1 扩展契约、重复判定。

### D3：token 单向流入工具调度（带外 kwarg + schema 排除）
`run()` / `run_stream()` 新增 `cancel_token: CancelToken | None = None`（None → 构造永不取消的默认 token）。工具调度 `_safe_dispatch(name, args, is_sub_agent, cancel_token)` 把 token 透传给 `dispatch`。

**token 注入机制（Decision，原 Open Question 升级而来）= 带外 kwarg + 注册标记 / 参数名约定 + schema 排除**：
- token **不是** LLM 提供的工具参数，而是运行时带外注入的 kwarg。`dispatch` 仅对「声明接受 token 的工具」（opt-in，按 `@tool` 注册标记或形参名 `cancel_token` 约定识别）在调用时显式追加 `cancel_token=token` kwarg；未声明的工具调用签名与行为不变。
- **必须同步修改 `tool_registry._build_schema`（行 84-101）排除该 token 参数**。现状 `_build_schema` 遍历 `inspect.signature` 的全部形参生成 `properties`，无默认值的形参进 `required`。若工具形参直接加 `cancel_token` 而不排除，它会被当作 `string` 必填字段暴露给 LLM，污染工具 schema、并诱导 LLM 为其编造取值。故 `_build_schema` 在构建 `properties` / `required` 时跳过被标记为「带外注入」的参数（与识别 opt-in 同一判据），保证 LLM 视角的 schema 不含 token。

**为何**：取消是运行时关注点，不应进入 LLM 的工具契约；带外 kwarg + schema 排除让 LLM 完全无感知，同时零改动未声明 token 的存量工具。把它从 Open Question 升级为 Decision，是因为「schema 暴露」是确定性副作用（`_build_schema` 必入 required），必须在 propose 阶段锁定排除机制而非留待实现期发现。
**Alternatives**：①不排除、让 token 进 schema——被否，污染契约、误导 LLM；②全局 `contextvar` 传 token 而不走 kwarg——被否，隐式传递难测试、与「单向显式传递」目标相悖。

### D3b：沙箱硬中止由 run_code 编排（容器句柄归属修正）
**句柄归属事实**：`run_code`（tools.py 行 50-70）内部 `client = SandboxClient(); ws_id = await client.create_workspace(...)`——容器 id（`ws_id`）是 `run_code` 的局部变量，`SandboxClient` 实例**不持有** `ws_id`。因此硬中止不能安在「`SandboxClient.exec` 自销毁」上（实例不知道要销毁哪个容器）。

**正确结构**：硬中止由 `run_code` 用 asyncio 编排：
- `run_code` 接受带外 `cancel_token`，并发跑两个任务——`exec_task = asyncio.create_task(client.exec(ws_id, ...))` 与一个观察 `token.is_cancelled()` 的 watcher 任务（轮询或事件驱动）。
- token 取消（或超 deadline）→ 取消 `exec_task` 的等待，并由 `run_code` 调 `client.destroy_workspace(ws_id)`（`docker rm -f`）强制销毁该容器、释放资源，返回取消结果。
- `finally` 仍兜底 `destroy_workspace(ws_id)`；`SandboxClient.destroy_workspace` 做成**幂等**（容器已不存在时 `rm -f` 不报错即可），保证取消路径已销毁后兜底二次销毁不抛。

`SandboxClient` 仅提供幂等 `destroy_workspace`，不承担「知道该销毁哪个容器」的编排职责——编排归 `run_code`（它持有 `ws_id`）。

**为何**：与代码真实结构吻合（`ws_id` 局部于 `run_code`）；agent-runtime.md 明确「取消必须真正释放资源，不只是停止等待」，`docker rm -f` 是最确定的中止手段；`run_code` 编排避免 `await communicate()` 阻塞期间错过取消。
**Alternatives**：①把 `ws_id` 塞进 `SandboxClient` 实例让 `exec` 自销毁——被否，与现有「一次性 client + 局部 ws_id」结构不符，且 `SandboxClient` 复用多容器时语义混乱；②仅 cancel asyncio 协程靠 `finally` 清理——被否，取消发生在 `communicate()` 阻塞中时 `finally` 可能延迟、容器悬挂。

### D4：cooperative + 硬 deadline 两层语义
- **cooperative**：主循环检查点（D2）+ 工具执行体周期性查询 `is_cancelled()`（D3）——这是「礼貌停止」，在安全点中止。
- **硬 deadline**：token 携带 `deadline`，到点 `is_cancelled()` 即 True，等同显式取消；对长时间无视协作查询的阻塞操作（如沙箱卡死），由消费方据 deadline 触发硬中止（`rm -f`）兜底。

**为何**：纯 cooperative 依赖被取消方主动检查，遇到「卡在系统调用里不回头」的执行无能为力；硬 deadline + 强制资源销毁提供兜底。两层正是 agent-runtime.md 写的「cooperative（协作停止）+ 硬 deadline 两层保护」。

### D5：trace 写入 cancelled 与时点（复用 log_run 既有字段）
`cancelled` 终止时 `stop_reason = StopReason.cancelled`，经现有 `log_run(..., stop_reason=...)` 出口写入 trace。取消发生的时点**直接复用 `log_run` 既有的 `ts`（时间戳）与 `elapsed_s`（相对任务开始的耗时）字段**——`cancelled` 终止那次运行的 `ts` / `elapsed_s` 即为取消时点的可追溯信息，**不新增专用 trace 字段、不新增出口**。

**为何**：与 AR1 其它终止原因写 trace 一致；agent-runtime.md 验收场景 12 要求「运行记录注明取消时间点」，现有 `ts` / `elapsed_s` 已满足，避免无谓扩展 trace schema。

## Risks / Trade-offs

- [`docker rm -f` 强制销毁可能丢失容器内未持久化的中间产物] → 取消语义本就是「立即停止」，丢弃中间产物符合预期；正常完成路径不受影响。
- [并发观察 token 与 `communicate()` 的竞态] → 用 `asyncio` 任务编排：取消触发即取消等待并执行 `rm -f`；`finally` 兜底再销毁一次，销毁做成幂等（容器已不存在时不报错），避免双重销毁异常。
- [契约一旦发布，后续 T2 / SB7 强依赖其稳定性] → design D1 明确锁定 token 接口形态（标志 + 单调 deadline + `is_cancelled()` 合并出口），波次 3 只新增「构造带 deadline 的 token」用法，不改接口；本 change spec 固化该契约的可观察行为。
- [不接受 token 的存量工具会在取消后仍跑完当轮] → 可接受：cooperative 语义下未声明 token 的工具在其调用边界结束后，下一次检查点即被 `cancelled` 截停；硬中止仅对声明接受 token 的工具（首批沙箱）生效。design 明确此边界。
- [`run_stream()` 取消后的流式收尾] → 取消在检查点命中即跳出循环、正常走 `done`/收尾出口，不向客户端泄漏半截事件。

## Open Questions

- MCP 连接的硬中止动作留待波次 3 MCP 功能复用本 token 接口实现；本 change 仅在沙箱上落实，spec 不约束 MCP 侧具体动作。

> 已关闭：token 注入机制（带外 kwarg + 注册标记/参数名约定 + `_build_schema` 排除）已在 D3 锁定为 Decision；沙箱硬中止用单步 `docker rm -f`、由 `run_code` 编排已在 D3b 锁定（`run_code` 持有 `ws_id`，`SandboxClient` 仅提供幂等销毁）。
