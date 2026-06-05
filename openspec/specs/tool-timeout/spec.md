# tool-timeout Specification

## Purpose
TBD - created by archiving change tool-timeout. Update Purpose after archive.
## Requirements
### Requirement: 单次工具调用受配置时限超时保护

单次工具调用 SHALL 受一个配置时限保护：在该时限内未完成时，工具调度边界 MUST 停止等待该工具，使主循环不被卡住的工具无限期阻塞。未超过时限的工具调用 MUST 与现状行为一致（正常返回结果，不受超时机制影响）。

#### Scenario: 工具在时限内完成正常返回

- **WHEN** 一个工具调用在配置时限内完成
- **THEN** 其结果照常返回给主循环，行为与未引入超时保护时一致

#### Scenario: 工具超过时限主循环停止等待

- **WHEN** 一个工具调用运行时间超过其有效超时时限
- **THEN** 工具调度边界停止等待该工具，主循环不再在该调用上无限期阻塞

### Requirement: 超时复用 AR19 cancel token 的 deadline 机制

超时 MUST 复用 AR19（`cancellation.py`）的 cancel token 契约实现，而非另造一套超时原语：为本次工具执行构造一个带 deadline（`now + timeout`）的 `CancelToken` 并按既有 out-of-band 注入规则提供给声明接受 token 的工具。该 per-tool token MUST 经 `parent` 链接（AR20 对 `cancellation.py` 增量补全的可选 `parent` 字段，`is_cancelled()` OR `parent.is_cancelled()`）挂接到 `run()`/`run_stream()` 已构造的 run 级 cancel token，使工具**同时**响应自身超时（deadline）与 run 级取消（parent），而非把 run 级 token 顶掉/旁路。时限到达时系统 SHALL 取消（`cancel()`）该 token，使协作式工具可在检查点观察到取消并停止。

#### Scenario: 为工具执行构造带 deadline 的 token

- **WHEN** 调度一个声明接受 cancel token 的工具并施加超时
- **THEN** 该次执行收到一个 deadline 设为 `now + 有效超时` 的 cancel token（复用 AR19 契约，不新增并行超时机制）

#### Scenario: 超时到达时取消 token

- **WHEN** 工具执行到达其超时 deadline 仍未完成
- **THEN** 系统取消该次执行的 cancel token，协作式工具在其检查点观察到 `is_cancelled()` 为真并停止

#### Scenario: run 级 token 取消经 parent 链接传播到在途工具

- **WHEN** 一个声明接受 cancel token 的工具在执行中，run 级 cancel token 在该工具自身 deadline 到达前被取消（如用户取消整个会话）
- **THEN** 该工具的 per-tool token 经 `parent` 链接 OR 上 run 级取消，工具在其检查点观察到 `is_cancelled()` 为真并停止（而非仅在自身超时时才感知）

### Requirement: 工具超时归一为 tool_timeout 错误返回给 LLM

工具调用超时 SHALL 被归一为错误分类 `tool_timeout`（复用 AR5 `agent-error-classification` 分类表中已定义的该分类码及其标志位），并以错误文本经工具调度边界的「失败结果」约定返回给 LLM，而非抛出异常杀死主循环或卡死。返回的错误文本 MUST 表明这是工具超时（区别于工具崩溃 `tool_crash`）。本能力是 AR5 所述「预留分类码 `tool_timeout` 的错误源接入」：接入后 `tool_timeout` MUST 成为可达分类。

#### Scenario: 超时归类为 tool_timeout

- **WHEN** 一个工具调用因超过时限被中止
- **THEN** 该次失败的错误分类码为 `tool_timeout`（取自 AR5 分类表，非 `tool_crash`、非 `unknown`）

#### Scenario: 超时以错误文本返回而非抛出

- **WHEN** 一个工具调用超时
- **THEN** 调度边界返回一段表明工具超时的错误文本（标记为失败），主循环据此继续而不被异常杀死

#### Scenario: tool_timeout 接入后成为可达分类

- **WHEN** 工具超时错误源接入后查询该次失败的分类
- **THEN** 返回 `tool_timeout`，且其恢复标志位与 AR5 分类表中该条目一致（不重定义标志位）

### Requirement: 超时时限可配置且 per-tool 覆盖全局默认

工具超时时限 SHALL 可配置：存在一个全局默认时限（默认 30 秒），其取值 SHALL 来自当前 agent 的配置（`agent.yaml` 的 `tool_default_timeout_seconds`）而非全局 `Settings`，未配置时回退至 30 秒默认。单个工具 MAY 经 `@tool(timeout=...)` 声明覆盖全局默认的 per-tool 时限。某工具的有效超时为：声明了 per-tool 时限则用之，否则用该 agent 解析出的全局默认。全局默认与 per-tool 时限元数据 MUST 可注入（模块级常量可 monkeypatch），不依赖全局可变状态，且 per-tool 超时元数据 MUST NOT 出现在 LLM 可见的工具 schema 中。

#### Scenario: 未声明 per-tool 时限用 agent 配置的全局默认

- **WHEN** 一个工具未经 `@tool(timeout=...)` 声明 per-tool 时限，且当前 agent 的 `agent.yaml` 声明 `tool_default_timeout_seconds: 15`
- **THEN** 其有效超时为 15 秒

#### Scenario: agent 未配置时回退 30 秒默认

- **WHEN** 当前 agent 未声明 `tool_default_timeout_seconds`，且某工具未声明 per-tool 时限
- **THEN** 其有效超时为 30 秒默认

#### Scenario: per-tool 时限覆盖全局默认

- **WHEN** 一个工具经 `@tool(timeout=5)` 声明 per-tool 时限
- **THEN** 其有效超时为 5 秒，覆盖全局默认

#### Scenario: 超时元数据不进 LLM schema

- **WHEN** 导出工具的 LLM schema
- **THEN** schema 中不包含该工具的超时时限元数据（与 `risk_level`/`connector` 一致，仅作调度时元数据）

### Requirement: 工具超时与沙箱执行超时（SB7）边界清晰

本能力 SHALL 仅在工具调度层施加通用超时（await 层停止等待 + cancel token 协作式中止），MUST NOT 实现沙箱容器的强制终止（`docker kill` SIGTERM→SIGKILL）。沙箱容器内执行的强制终止与容器清理属 SB7（沙箱执行超时）职责，是本能力在 `run_code` 场景的特化，不在本能力范围。对于不响应取消、无法被安全中止的工具，本能力 SHALL 保证主循环停止等待并返回 `tool_timeout`，但 MAY NOT 立即终止其后台执行（后台真正终止由协作式工具自身或 SB7 容器侧负责）。

#### Scenario: 本能力不执行 docker kill

- **WHEN** 任一工具（含 run_code）发生工具层超时
- **THEN** 本能力仅停止等待并归类返回 `tool_timeout`，不执行 `docker kill` 等容器强制终止动作（该动作归 SB7）

#### Scenario: 不协作工具仅保证主循环不阻塞

- **WHEN** 一个不查询 cancel token 的工具超时
- **THEN** 主循环停止等待并返回 `tool_timeout` 错误；该工具的后台协程是否立即终止不由本能力保证（划归协作式工具自身或 SB7）

