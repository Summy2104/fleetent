## Why

2026-06-11 dev-intern 实测：进程收到 SIGUSR1 开始优雅排水（`agent_drain_started active_runs=3`），
退出路径上事件循环对**从未被关闭的** MCP Streamable HTTP 传输异步生成器强制收尸
（`shutdown_asyncgens` 跨 task `athrow`）→ anyio `Attempted to exit cancel scope in a different
task` → `BaseExceptionGroup` 反向打挂主 task 的 cancel scope → **进程 exit 1，3 个在飞对话全丢**。
结论：**当前每一次优雅重启都以崩溃收场**，仅被 systemd `Restart=on-failure` 掩盖。

逐项对账运行时生命周期管理后的定性：**架构存在且大体正确**（IM supervisor 每连接一个 owner
task ✅、调度器接入 `AgentRuntime.stop()` ✅、排水顺序"先停入口再排干" ✅）；**MCP 客户端是唯一
游离在该架构之外的子系统**，叠加关停路径缺少错误舱壁：

1. **spec 有、实现漏**：`mcp-session-continuity` 已明文要求「关停时释放会话，失败仅记日志不阻断」，
   但实现侧 `close()`（`integrations/mcp/client.py:289`）**全仓零调用**——死代码，会话在任何关闭
   路径上都不被释放；
2. **spec 规定的机制本身不可实现自身要求**：spec 把会话生命周期钉在「统一 `AsyncExitStack`」上，
   而 SDK 三种 transport（stdio/sse/streamable-http）内部均为 anyio cancel scope/task group，
   **要求 enter/exit 同 task**；共享栈的 enter 发生在"谁先用谁的 task"（boot task、Slack 消息
   处理 task 的懒重连），任何统一解栈必然跨 task 违例——规定机制与「best-effort 安全释放」目标
   在 anyio 语义下结构性冲突；
3. **懒重连泄漏**：`_reopen_session` 只开新不关旧，死会话的传输 CM 永久滞留；
4. **无舱壁**：单个组件的收尾异常以 `BaseExceptionGroup` 直冲顶层、改变进程退出码——违反项目
   风格铁律「不可注入的全局可变状态」（AGENTS.md）的 MCP 模块级 `_exit_stack` 正是事故载体。

本 change 把 MCP 子系统**纳编**进既有生命周期架构（per-session owner task），给关停链补**舱壁**，
并把隐含规则固化为**护栏**——修"类"，不是修"例"。系统未发版，是做此事的最佳窗口。

## What Changes

- **会话宿主重构**（`integrations/mcp/client.py`）：每个 MCP 会话由专属 asyncio task 全权拥有——
  宿主 task 内 `async with transport_cm` + `async with ClientSession` → `initialize` → set ready
  → 驻留 `close_event` → 同 task 内退出。`_active_sessions[(scope, server_id)]` 改存宿主句柄；
  **删除模块级 `_exit_stack` / `get_exit_stack()`**。三种 transport 统一走宿主。
- **真正被调用的 `aclose_all()`**：并发关闭全部宿主（set event → await task，每宿主超时 5s，
  超时 `cancel()` 兜底）；替换死代码 `close()`（零调用方，无 shim 需要）。
- **关停接线（两处）**：agent 侧 `runtime/agent_app._drain_and_exit` 在排干在飞 run **之后**调用
  `aclose_all()`（顺序：停 IM/调度入口 → 排干 → 关 MCP → 退出）；platform 侧 `server.py` lifespan
  shutdown 同样调用（platform 经 `connector_management/mcp_runtime.register_all` 也持有会话）。
- **懒重连关旧**：`_reopen_session` 先关旧宿主（失败仅记日志）再开新会话。
- **关停舱壁**：`_drain_and_exit` / `AgentRuntime.stop()` 链上每一步（IM、调度器、MCP）独立
  try/except + 超时，失败记日志继续下一步。**不变式：任何组件的收尾错误不得改变进程退出码、
  不得波及其它组件**；优雅排水路径以 exit 0 结束。
- **契约固化 + 护栏**：AGENTS.md 架构契约区追加「长生命周期异步资源必须有唯一 owner task；
  谁打开谁关闭；禁止模块级持有活资源的全局单例」；`tests/unit/test_module_dependency_guardrails.py`
  新增护栏：src 模块作用域禁止 `AsyncExitStack` 持有连接类资源（现存唯一违例即本 change 移除的
  `_exit_stack`，护栏先红后绿）。

## Capabilities

### New Capabilities
<!-- 无新增 capability；对既有 MCP 会话持有/关停语义与运行时排水链做结构性修订 -->

### Modified Capabilities

- `mcp-session-continuity`：会话持有机制由「统一 AsyncExitStack」改为「per-session owner task
  （宿主）」，同 task enter/exit；关停释放改经 `aclose_all()`（best-effort + 每宿主超时兜底），
  并真正接入 agent/platform 两侧关停链；懒重连补「先关旧宿主」语义。
- `agent-runtime-cli`：SIGUSR1 优雅排水链增加「排干后释放 MCP 会话」步骤与逐步舱壁；新增
  退出码不变式（优雅路径 exit 0，收尾错误不得改变退出码）。
- `module-dependency-guardrails`：新增「模块级活异步资源单例」护栏 requirement。

## Impact

- **owning package**：`integrations/mcp`（会话宿主 + aclose_all）+ `runtime`（agent_app 排水接线
  与舱壁）+ `server.py`（platform lifespan 接线）+ `tests/unit`（护栏）。
- **public API surface**：`integrations.mcp` 公共面新增 `aclose_all()`、移除死代码 `close()`
  （零调用方，无兼容性影响）；`_open_session_for`/`_call_via_session`/懒重连等内部协作面签名不变
  （调用方只消费 session 句柄）。`AgentRuntime.stop()` 行为增强（含舱壁），签名不变。
- **owned tables**：无。
- **config namespace**：无（宿主关闭超时为模块内可注入常量，便于测试 monkeypatch）。
- **cross-module dependencies**：`runtime.agent_app → integrations.mcp` 公共 API（agent 运行时内部，
  方向合法）；`server.py → integrations.mcp`（platform→agent-runtime 方向，合法）。零新增反向依赖；
  `im_gateway`/`cron_scheduler` 不触碰。
- **migration / shim plan**：无表/配置变更；`close()` 删除无需 shim（零调用方，grep 验证）。
- **验证基线**：① 对 dev-intern 连发 20 次 SIGUSR1 优雅重启 → **每次 exit 0、零 traceback、
  Slack 连接每次恢复**；② 注入「关闭必抛错」的假 transport → 进程存活、仅 warning 日志；
  ③ 单测断言三种 transport 的 enter/exit 同 task；④ `make test-pr` + integration 对照 main
  基线无新增失败。关联 Jira：**AAA-8050**（重任务静默失败的真凶之一：进程猝死）。
