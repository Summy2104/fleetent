## Why

工具调用当前**没有时限**：`_safe_dispatch`（`agent_loop.py` 行 185-214）把 `dispatch` 的结果 `await` 出来——若一个工具（网络 IO、外部进程、`run_code` 沙箱、MCP 调用）卡住或永不返回，主循环就在该 `await` 上**无限期阻塞**，整个 agent 会话挂死，用户既得不到结果也得不到错误。`docs/capabilities/tools.md`（行 75）把「工具超时保护」列为 v1.0 规划：「每次 `dispatch` 设置 per-tool 超时（可在 `@tool` 声明，默认 30s），超时后返回 `tool_timeout` 错误给 LLM」。

波次 2 的 AR19（`cancellation-propagation`，已合入 `cancellation.py`）已把 cancel token 的接口**对外发布为契约**：其 docstring（`cancellation.py` 行 11-12）明确「a timeout is just `CancelToken(deadline=now + timeout)`」，并点名 T2 / SB7 复用。波次 2 的 AR5（`agent-error-classification`，已归档）已在分类表里**预留** `tool_timeout` 分类码及其标志位，但 AR5 spec 的「预留分类码不被主动返回」要求 `classify()` 在对应错误源接入前**不得**返回它。本 change（T2）正是接入该错误源的功能：它构造带 deadline 的 token、把工具超时归一为 `tool_timeout`，让 AR5 的预留码首次成为可达分类。

## What Changes

- 在工具调度边界（`_safe_dispatch` / `dispatch` 调用点）为**单次工具调用**施加超时保护：超过配置时限即视为超时。
- 超时的实现**复用 AR19 cancel token 契约**——为本次工具执行构造一个 `CancelToken(deadline=now + timeout)`，并在 asyncio await 层将工具执行与该 deadline 竞速；到点后 `cancel()` token（协作式停止）并停止等待，**不再无限阻塞**。
- 超时被归一为**一类错误** `tool_timeout`（接 AR5 分类表的预留码），以**错误文本返回给 LLM**（沿用 `_safe_dispatch` 的 `(error_text, failed=True)` 约定），而非抛出杀死主循环或卡死。本 change 使 `tool_timeout` 首次成为 `classify()`（或等价的工具层归类入口）可达的分类。
- **超时时限可配置**：全局默认（30s，对齐 tools.md）+ **per-tool 覆盖**（`@tool(timeout=...)` 声明）。默认值与全局配置项**可注入**（模块级常量，可 monkeypatch），无全局可变状态。
- 与 **SB7（沙箱执行超时）划清边界**：T2 是**工具层通用超时**，在 await 层竞速并经 cancel token 协作式中止任意工具；SB7 是 `run_code` 沙箱**容器内执行**的**强制终止**（`docker kill` SIGTERM→SIGKILL），是 T2 在 run_code 场景的特化（见 design 边界小节）。本 change 不实现 `docker kill`。

## Capabilities

### New Capabilities
- `tool-timeout`: 单次工具调用超过配置时限（全局默认 + per-tool 覆盖）时，经 AR19 cancel token 的 deadline 协作式中止并停止等待，将超时归一为 `tool_timeout` 错误（AR5 预留码首次接入）返回给 LLM，使主循环不被卡死的工具阻塞。

### Modified Capabilities
<!-- 不 MODIFY 既有 spec。`tool_timeout` 错误码与标志位已存在于 AR5（agent-error-classification）分类表，本 change 仅「接入错误源使其可达」，属新增可观察行为，落在本 change 新 capability `tool-timeout` 下以 ADDED 表达；不 MODIFY agent-error-classification，避免与并行 change 就同一分类表需求互相覆盖、产生归档顺序敏感。 -->

## Impact

- **代码**：
  - 工具调度边界（`src/fleetent/agent_loop.py` 的 `_safe_dispatch`）：为单次工具执行施加超时竞速，超时则 `cancel()` token、停止等待、返回 `tool_timeout` 错误文本。
  - 工具注册（`src/fleetent/tool_registry.py`）：`@tool(timeout=...)` 声明 per-tool 时限，记录到与 `_risk_levels` 平行的元数据表，`get_timeout(name)` 查询；超时元数据**不进** LLM schema。
  - 工具层超时归类入口：超时异常（`asyncio.TimeoutError` / `TimeoutError`）归一为 `ErrorCategory.tool_timeout`（接 AR5 分类表），具体接入点（扩展 `error_classifier._categorize` 还是工具层单独映射）在 design D 决定。
- **配置**：新增全局默认工具超时项（默认 30s），可注入/可覆盖；具体承载位置（模块级常量 vs `config.Settings` 字段）在 design 定。
- **测试**：新增/扩充 `tests/test_tool_registry.py`（`@tool(timeout=...)` 记录与查询、不进 schema）、`tests/test_agent_loop.py` 或新建超时测试（慢工具被超时、超时归类 `tool_timeout`、per-tool 覆盖全局、token 被 cancel）。异步超时**用可控方式测**（注入极短超时 / 可控的慢工具 stub，不真实 sleep 长时间）；LLM 调用 mock；路径与配置隔离到 tmp_path / monkeypatch。
- **不影响**：未超时的工具调用路径（行为不变）、SB7 的 `docker kill`（不在本 change）、AR19 token 接口（仅复用，不改）、AR5 分类表结构（仅令预留码可达，不改表）。

## Dependencies

- **`src/fleetent/tool_registry.py`**（`dispatch` 工具分发、`@tool` 元数据表范式）：新增 per-tool `timeout` 元数据，复用与 `_risk_levels`/`_connectors` 平行、不进 schema 的既有范式。
- **`src/fleetent/cancellation.py` / AR19（`cancellation-propagation`）**：复用 `CancelToken(deadline=now+timeout)` 契约作为超时的统一机制；AR19 必须先合入（已满足）。本 change 的 per-tool deadline token MUST 经 AR20 补全的 `parent` 链接挂接 `run()`/`run_stream()` 已构造的 run 级 cancel token，使工具同时响应自身超时与 run 级取消（不把 run 级 token 顶掉/旁路）。
- **`sub-agent-lifecycle`（AR20）**：复用其对 `cancellation.py` 增量补全的 `parent` 链接原语（`CancelToken` 可选 `parent` 字段，`is_cancelled()` OR `parent.is_cancelled()`，纯加法、向后兼容）来合并「per-tool deadline」与「run 级取消」双取消源。本 change 仅为消费方，不重复定义该原语；归档顺序上 AR20 对 `cancellation.py` 的 `parent` 增量须先就位。
- **AR5（`openspec/specs/agent-error-classification/spec.md`）**：超时归入既有预留分类码 `tool_timeout`；本 change 是 AR5「预留分类码不被主动返回」所指的「错误源接入」，使该码首次可达。
