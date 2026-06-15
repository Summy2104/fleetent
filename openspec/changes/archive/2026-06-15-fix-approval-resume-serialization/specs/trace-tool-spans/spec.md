## MODIFIED Requirements

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
