# agent-runtime-logging

## Purpose

规范 agent 运行时各模块（loop、context、sub_agent、snapshot、budget、loop_detector、guardrails、hygiene、error）的结构化日志输出，统一日志器命名、级别和字段约定，便于可观测性与故障排查。

## Requirements

### Requirement: runtime.loop 记录 agent 运行生命周期事件

`runtime/loop.py` SHALL 使用 `get_logger("runtime.loop")` 记录 agent 运行的关键节点与中间状态。

#### Scenario: run 开始记录 info
- **WHEN** `run()` 或 `run_stream()` 被调用
- **THEN** 以 `info` 级别记录事件，fields 包含 `agent`、`session_id`、`max_turns`、`max_tokens`

#### Scenario: run 正常结束记录 info
- **WHEN** agent 循环以任意 `StopReason` 退出
- **THEN** 以 `info` 级别记录事件，fields 包含 `agent`、`stop_reason`、`turns`、`tokens`

#### Scenario: 每轮迭代开始记录 debug
- **WHEN** 循环进入新一轮迭代
- **THEN** 以 `debug` 级别记录事件，fields 包含 `turn`、`session_id`

#### Scenario: 工具调用发起与完成记录 debug
- **WHEN** 工具调用发起或完成
- **THEN** 以 `debug` 级别分别记录，发起含 `tool_name`、`turn`，完成含 `tool_name`、`duration_ms`

#### Scenario: 工具调用原始结果记录 trace
- **WHEN** 工具调用返回结果
- **THEN** 以 `trace` 级别记录，fields 包含 `tool_name`、`result_preview`（截断 200 字符）

#### Scenario: 模型切换记录 warn
- **WHEN** 发生 fallback 模型切换
- **THEN** 以 `warn` 级别记录，fields 包含 `from_model`、`to_model`、`reason`

### Requirement: runtime.context 记录压缩事件

`runtime/context.py` SHALL 使用 `get_logger("runtime.context")` 记录上下文压缩的触发与结果。

#### Scenario: 压缩触发记录 info
- **WHEN** 上下文压缩被触发
- **THEN** 以 `info` 级别记录，fields 包含 `session_id`、`messages_before`、`messages_after`

#### Scenario: 压缩异常记录 warn
- **WHEN** 压缩过程出现异常（model resolve 失败、summary 为空等）
- **THEN** 以 `warn` 级别记录，fields 包含 `error`

### Requirement: runtime.sub_agent 记录子 agent 生命周期

`runtime/sub_agent.py` 和 `runtime/sub_agent_lifecycle.py` SHALL 使用 `get_logger("runtime.sub_agent")` 记录子 agent 启动、完成和异常状态。

#### Scenario: 子 agent 启动记录 info
- **WHEN** 子 agent 任务开始执行
- **THEN** 以 `info` 级别记录，fields 包含 `name`、`depth`

#### Scenario: 子 agent 完成记录 info
- **WHEN** 子 agent 任务正常完成
- **THEN** 以 `info` 级别记录，fields 包含 `name`、`duration_ms`

#### Scenario: 非法状态跳转记录 warn
- **WHEN** `SubAgentLifecycle` 发生非法状态转换
- **THEN** 以 `warn` 级别记录，fields 包含 `src`、`dst`

#### Scenario: 子任务失败记录 warn
- **WHEN** 子 agent 任务抛出异常
- **THEN** 以 `warn` 级别记录，fields 包含 `task`、`error`

### Requirement: runtime.snapshot 记录快照加载结果

`runtime/snapshot.py` SHALL 使用 `get_logger("runtime.snapshot")` 记录 agent 快照的加载状态。

#### Scenario: 快照加载成功记录 info
- **WHEN** `load_active()` 成功返回快照
- **THEN** 以 `info` 级别记录，fields 包含 `agent`、`version_id`

#### Scenario: 快照不存在记录 warn
- **WHEN** `load_active()` 返回 None
- **THEN** 以 `warn` 级别记录，fields 包含 `agent`

#### Scenario: 快照加载异常记录 error
- **WHEN** 加载过程抛出异常
- **THEN** 以 `error` 级别记录，fields 包含 `agent`、`exception`

### Requirement: runtime.budget 记录预算耗尽事件

`runtime/budget.py` SHALL 使用 `get_logger("runtime.budget")` 记录预算维度耗尽。

#### Scenario: 预算耗尽记录 warn
- **WHEN** `BudgetChecker.check()` 判定某维度已耗尽
- **THEN** 以 `warn` 级别记录，fields 包含 `dimension`、`limit`、`actual`

### Requirement: runtime.loop_detector 记录循环检测事件

`runtime/loop_detector.py` SHALL 使用 `get_logger("runtime.loop_detector")` 记录循环检测的触发与终止。

#### Scenario: 首次检测到循环记录 warn
- **WHEN** 循环检测器首次触发（注入警告阶段）
- **THEN** 以 `warn` 级别记录，fields 包含 `signal`、`tool_name`、`count`

#### Scenario: 循环触发终止记录 error
- **WHEN** 循环检测器二次触发导致运行停止
- **THEN** 以 `error` 级别记录，fields 包含 `signal`、`tool_name`、`count`

### Requirement: runtime.guardrails 记录工具调用 guardrail 事件

`runtime/tool_guardrails.py` SHALL 使用 `get_logger("runtime.guardrails")` 记录重复工具调用的短路与停止。

#### Scenario: 工具调用短路记录 warn
- **WHEN** `evaluate_guardrail()` 返回 `GuardrailAction.short_circuit`
- **THEN** 以 `warn` 级别记录，fields 包含 `tool_name`、`consecutive_count`

#### Scenario: 工具调用强制停止记录 error
- **WHEN** `evaluate_guardrail()` 返回 `GuardrailAction.stop`
- **THEN** 以 `error` 级别记录，fields 包含 `tool_name`、`consecutive_count`

### Requirement: runtime.hygiene 记录消息修复事件

`runtime/message_hygiene.py` SHALL 使用 `get_logger("runtime.hygiene")` 记录消息修复。

#### Scenario: 有修复时记录 warn
- **WHEN** `sanitize()` 返回的 `HygieneReport.changed()` 为 True
- **THEN** 以 `warn` 级别记录，fields 包含 `repairs`（各 RepairKind 的计数 dict）

#### Scenario: 校验失败记录 error
- **WHEN** `_validate_structure()` 抛出 `MessageContractError`
- **THEN** 以 `error` 级别记录，fields 包含 `exception`

### Requirement: runtime.error 记录错误分类结果

`runtime/error_classifier.py` SHALL 使用 `get_logger("runtime.error")` 记录错误分类。

#### Scenario: 错误分类记录 debug
- **WHEN** `classify()` 对一个异常完成分类
- **THEN** 以 `debug` 级别记录，fields 包含 `category`、`should_retry`、`should_compress`、`should_switch_model`
