## Why

LLM 一轮可返回**多个 `tool_calls`**，但主循环（`agent_loop.run()` / `run_stream()`）当前**顺序逐个** dispatch（`agent_loop.py` 行 ~739 `for tc in msg.tool_calls` → ~811/~821 `_safe_dispatch`）。当一轮内有多个相互独立的工具（如同时查三个数据源、并行抓多个 URL），顺序执行使本轮工具耗时线性叠加，端到端时延高、资源闲置。

这是 AR3（波次 4，Track A 收尾，依赖 AR1·AR6·AR19）。它把**同一轮内**的多个 `tool_calls` 从顺序 dispatch 改为**并行调度执行**（`asyncio.gather`），并把结果**按原 `tool_calls` 顺序回填**进 `messages`，保持 OpenAI 的 assistant→tool 配对与顺序合法（AR6 sanitize 不破）。`run()` 与 `run_stream()` 两条路径都接。

> AR3 是 Track A 关键路径的最后一环：它复用而非重做 AR1（终止/`cancelled` 原因码）、AR6（消息卫生/tool-pair 完整性）、AR19（`CancelToken`，`_safe_dispatch` 已接 + T2 per-tool 超时）。本 change 不引入新机制，只把既有的「单工具调度」编排为「一批工具并行调度 + 原序回填」。

## What Changes

- **并行调度同一轮内的多个 `tool_calls`**：把 `run()`（行 ~739 起）与 `run_stream()`（行 ~1117 起）的 `for tc in tool_calls` 顺序 dispatch 改为：对本轮非短路（AR10 guardrail 通过）的工具调用，用 `asyncio.gather` 并发执行 `_safe_dispatch`，结果**按原 `tool_calls` 索引顺序**回填为 `role:"tool"` 消息。
- **原序回填保序**：`asyncio.gather` 的返回顺序即入参顺序（非完成序），据此保证 assistant（N 个 `tool_calls`）后紧跟 N 条 tool 结果、与 `tool_call_id` 一一配对、顺序 = 原 `tool_calls` 顺序。
- **取消传播（复用 AR19）**：并行批次共享同一 run-level `cancel_token`（行 661/992 的 `token`）；`_safe_dispatch` 已为每个工具派生带 deadline 的 child token（行 314）。取消 / deadline 命中时批次内所有在途工具一并中止（`run_code` 走 AR19 `docker rm -f`），批次以合法的消息序列收尾——N 个 `tool_calls` 要么都有对应 tool 结果消息（含取消占位），不泄漏半截 tool-pair。
- **审批策略（permission_gate）**：一轮内多个 medium/high 风险工具的审批**串行逐个过 gate**，全部批准后再并行执行（被拒沿用现有 `approval_rejected` 占位结果）；不并发触发 `_default_gate.request_approval`。
- **失败隔离与计数**：批次内单工具失败（`_safe_dispatch` 归一化为 `failed=True`）不影响同批其余工具；`consecutive_failures` 与 AR4/AR10 loop-detection 按**逐结果**记录，语义与顺序执行等价。
- **并发上限**：单轮并行度有可配置上限（默认值见 design D7），超过上限的工具分批执行，避免 N 工具打爆资源。
- **`run_stream` 流式顺序**：并行执行期 `tool_call` / `tool_result` 流式事件**按原 `tool_calls` 顺序** yield，客户端语义可理解，不泄漏半截事件。
- **N=1 等价**：单 `tool_call`（N=1）路径行为须与现状**字节级等价**（messages 内容、事件顺序、计数不变）。

## Capabilities

### New Capabilities
- `tool-parallel-dispatch`: 同一轮内多个 `tool_calls` 的并行调度执行与按原序回填。涵盖：并行执行（`asyncio.gather`）、原序回填保序（tool-pair 配对 / 顺序合法、AR6 不破）、并行批次取消传播（共享 run-level token，取消时全批中止、收尾消息合法）、多风险工具审批策略（审批串行、执行并行）、单工具失败隔离与 `consecutive_failures` / loop-detection 逐结果计数、单轮并发上限（可配置默认值）、`run_stream` 并行期流式事件原序、N=1 与现状字节级等价。

### Modified Capabilities
<!-- 无。AR3 不改既有 spec 的可观察需求：单 tool_call 行为字节级不变（Non-Goal）；不改工具注册/schema/访问控制；终止/取消/超时/卫生的既有需求（agent-loop-termination、agent-cancellation-propagation、tool-timeout、message-hygiene）均原样复用，不 MODIFY。新行为全部 ADDED 到新 capability `tool-parallel-dispatch`。波次 2 教训：新 capability spec 只允许 ADDED，MODIFIED 必须放对应既有 capability 的 delta 目录；本 change 不需要 MODIFIED。 -->

## Impact

- **代码**：
  - 修改 `src/fleetent/agent_loop.py`：
    - `run()`（行 ~739–843）：把 `for tc in msg.tool_calls` 的顺序 dispatch 重构为两阶段——**阶段一**（串行、保持原序）对每个 `tc` 跑 AR10 guardrail 判定与（medium/high）permission_gate 审批，确定本轮要执行的工具集合与各自占位（短路 / 拒批的工具直接产出占位结果，不进并行批）；**阶段二**对待执行集合用 `asyncio.gather`（受并发上限约束、可分批）并发跑 `_safe_dispatch`；**阶段三**按原 `tool_calls` 索引顺序回填 tool 结果消息、`record_tool_call`、`consecutive_failures` 累计。
    - `run_stream()`（行 ~1117–1160）：同构重构；`tool_call` / `tool_result` 流式事件按原序 yield（执行虽并行，事件按索引顺序发出）。
    - 新增并发上限读取（`Settings` 字段，见下）；`sub_agent` 特例（`_SUB_AGENT_TOOL`，行 764）保持现有 `SubAgentExecutor` 行为，不被 AR3 二次并行（见 design D6）。
  - 修改 `src/fleetent/config.py`：`Settings` 新增 `agent_tool_parallel_max`（单轮并行度上限，默认值见 design D7），可经 `.env` / `settings.yaml` 覆盖、可 monkeypatch 注入。
- **配置**：新增一项部署级配置 `agent_tool_parallel_max`（默认见 D7）；不引入新依赖（`asyncio` 标准库）。
- **测试**：
  - `tests/test_agent_loop.py` 补充：N=1 与现状字节级等价；N>1 并行执行 + 原序回填（tool-pair 配对、顺序）；批次内取消 → 全批中止、收尾消息合法（无半截 tool-pair）；多 medium/high 工具审批串行、全批准后并行；单工具失败不影响同批其余、`consecutive_failures` 逐结果正确；并发上限分批；`run_stream` 并行期事件按原序。LLM 调用按规范 mock（patch `get_async_client_and_config`）。
  - `tests/test_config.py`（若存在）补充新配置项默认值与覆盖。
- **不影响**：单 `tool_call`（N=1）路径字节级不变；工具注册 / schema / `check_tool_access` 访问控制不变；AR1 终止判定、AR19 token 接口、AR6 sanitize、T2 per-tool 超时、permission_gate 的 asyncio.Event 门、`SubAgentExecutor` 的深度约束（最大深度 1）均不变；不做跨轮并行（只并行同一轮内的多 `tool_calls`）。
