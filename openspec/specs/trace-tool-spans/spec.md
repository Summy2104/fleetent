# trace-tool-spans

## Purpose

工具调用级 trace 事件（真实执行才记、脱敏入参、成败/耗时/风险）与 run 级事件的 session 归属绑定，使任一会话的执行轨迹可由一条 SQL 重建。
## Requirements
### Requirement: 真实执行的工具调用写 tool_call trace 事件

agent loop SHALL 在工具**真实执行完成后**（`run` 与 `run_stream` 两路，含恢复 run 与 sub_agent run）为每次工具调用向 traces 写一条 `event_type="tool_call"` 事件，payload 至少含 `{tool_name, tool_call_id, args_summary, failed, duration_ms, risk}`。审批挂起 placeholder、guardrail 短路、pre_tool_use deny 等未真实执行的 slot MUST NOT 产生 tool_call 事件。trace 写入失败 MUST 仅记 warning，MUST NOT 影响工具结果与 run 继续。

该 best-effort 容错 MUST 覆盖 `args_summary` 的**构建**（不仅是落库）：args_summary 序列化遇到任意不可序列化的入参值时 MUST 降级（如以其字符串形式表示）而非抛异常，确保 trace 记录绝不中断工具结果或 run/恢复 run 的继续。此外，工具分发为受门控/opt-in 工具**注入的 out-of-band 上下文（`tool_context`、`cancel_token`）MUST NOT 出现在持久化的 `args_summary` 中**，且分发 MUST NOT 因注入而改写调用方传入的入参映射——args_summary 只反映模型提供的入参。

#### Scenario: 成功执行记录事件

- **WHEN** 某 run 真实执行了 `send_file` 且成功
- **THEN** traces 出现一条 `tool_call` 事件，payload 含 `tool_name="send_file"`、`failed=false` 与耗时

#### Scenario: 失败执行如实记录

- **WHEN** 某工具执行抛错或返回失败
- **THEN** 对应 `tool_call` 事件 `failed=true`

#### Scenario: 审批 placeholder 不产生事件

- **WHEN** 某工具调用因审批挂起写入 `awaiting_human_approval` placeholder
- **THEN** 本轮不为该 tool_call_id 产生 `tool_call` 事件（恢复后真实执行时才记录）

#### Scenario: trace 写入失败不影响 run

- **WHEN** traces 落库抛异常
- **THEN** 工具结果照常返回、run 继续，仅记一条 warning 日志

#### Scenario: 恢复执行的 args_summary 不含注入上下文且不崩

- **WHEN** 审批恢复以 dict 入参经分发执行受门控工具（分发会注入 `tool_context`），随后记录该恢复执行的 `tool_call` 事件
- **THEN** `args_summary` 不含 `tool_context`/`cancel_token` 等注入对象、构建不抛异常，恢复 run 正常续跑并保存

### Requirement: tool_call 入参摘要脱敏且有界

`tool_call` 事件的 `args_summary` MUST 经统一工具入参脱敏基线（tool-arg-secret-redaction）处理后序列化，且 MUST 截断到固定上限（2KB），防止 secret 与大参数落盘。

#### Scenario: secret 参数不落 traces

- **WHEN** 工具入参含 `api_key` / token 类字段
- **THEN** `args_summary` 中对应值已被脱敏，traces 中无明文

#### Scenario: 大参数截断

- **WHEN** 工具入参序列化后超过上限（如长代码字符串）
- **THEN** `args_summary` 被截断到上限并带截断标记

### Requirement: trace 事件绑定 session_id

run 级事件（`agent_run_completed`、`injected_context`、`skill_hit`）与 `tool_call` 事件 SHALL 在会话上下文可得时携带 `session_id` 写入 traces（schema 列已存在，本要求约束写入点）。按 `session_id` 查询 MUST 能取回该会话的完整事件序列。无会话的运行路径（如纯 CLI 单次调用）session_id 允许为空。

#### Scenario: 会话内事件可按 session 重建

- **WHEN** 某 Slack 会话的一次 run 产生 injected_context、两次 tool_call 与 agent_run_completed
- **THEN** 按该 session_id 查询 traces 返回这四条事件，时间有序

#### Scenario: 恢复 run 的事件归属同一会话

- **WHEN** 一次审批挂起后恢复的 run 真实执行了 pending 工具
- **THEN** 其 tool_call 事件的 session_id 与原会话一致

