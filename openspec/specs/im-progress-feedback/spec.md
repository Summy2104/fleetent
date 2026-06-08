## Purpose

Provide real-time progress feedback to IM users during agent runs by propagating an optional
`progress_func` callback through the agent pipeline to IM adapters, enabling platform-native
indicators (e.g., Slack message updates, Telegram typing action) when tools are invoked.

## Requirements

### Requirement: NormalizedMessage 携带可选 progress_func 回调

`NormalizedMessage` SHALL 新增可选字段 `progress_func: Callable[[dict], Awaitable[None]] | None`，
默认值为 `None`。当为 `None` 时，所有行为与当前版本完全一致，不引入任何副作用。

#### Scenario: 不传 progress_func 时行为不变

- **WHEN** IM 适配器构造 `NormalizedMessage` 时未传 `progress_func`
- **THEN** normalizer.route() 执行与当前完全相同，不产生任何进度事件

#### Scenario: 传入 progress_func 时，工具调用开始时被调用

- **WHEN** IM 适配器传入非 `None` 的 `progress_func`，agent 在 run 过程中发起一次工具调用
- **THEN** 在该工具调用实际执行前，`progress_func({"type": "tool_call", "name": "<tool_name>"})` 被 await
- **AND** 事件 dict 仅含 `type` 和 `name` 字段，不含工具参数或任何敏感信息

### Requirement: agent_loop.run() 透传 progress_func 到工具调度层

`agent_loop.run()` 和内部 `_run_inner()` SHALL 接受 `progress_func` 参数，
并在 `_plan_run_slots()` 确定工具调用名称后、实际执行前以 `tool_call` 事件调用之。

#### Scenario: 工具调用触发 progress 事件

- **WHEN** `run()` 收到非 `None` 的 `progress_func`，agent loop 决定调用工具 `web_search`
- **THEN** `progress_func({"type": "tool_call", "name": "web_search"})` 在工具执行前被 await

#### Scenario: progress_func 异常不中断 agent run

- **WHEN** `progress_func` 调用时抛出异常（如网络错误）
- **THEN** 异常被捕获并 log，agent run 继续正常执行，不因 progress 失败而中断

#### Scenario: sub_agent 内工具调用不触发父 progress_func

- **WHEN** agent run 中包含 sub_agent 调用，sub_agent 内部执行工具
- **THEN** 仅顶层 agent 的工具调用触发 `progress_func`，sub_agent 的工具调用不触发

### Requirement: Slack 适配器立即发送占位消息并原地更新

Slack 适配器 SHALL 在收到消息时立即发送一条占位消息，并在 agent 运行期间
通过 `chat.update` 原地更新，展示当前正在调用的工具名称；最终回复替换该占位消息。

#### Scenario: 消息到达时立即发送占位

- **WHEN** Slack handle_message 收到用户消息
- **THEN** 在进入 session_lock / agent run 前，发送一条 "🤔 思考中…" 占位消息至目标 thread
- **AND** 记录返回的 `ts`（消息 ID），用于后续更新

#### Scenario: 工具调用时更新占位消息

- **WHEN** `progress_func` 收到 `{"type": "tool_call", "name": "some_tool"}` 事件
- **THEN** 若距上次 `chat.update` 超过 1 秒，调用 `chat.update` 将消息更新为 "🔧 正在调用 some_tool…"

#### Scenario: 频繁工具调用时节流

- **WHEN** 连续两次 `tool_call` 事件间隔不足 1 秒
- **THEN** 第二次不触发 `chat.update`，避免超出 Slack API 频率限制（~1次/秒/channel）

#### Scenario: agent 完成后最终回复替换占位消息

- **WHEN** agent run 完成，`reply_func` 被调用
- **THEN** 通过 `chat.update` 将占位消息替换为完整回复内容
- **AND** 不产生新消息，用户看到的仍是同一条消息（内容变为最终答案）

#### Scenario: Slack API 失败时降级为静默

- **WHEN** 占位消息发送失败（如网络错误或权限问题）
- **THEN** 适配器 log 错误并降级：不发占位消息，agent run 继续，完成后 reply_func 照常发送最终回复

### Requirement: Telegram 适配器在 agent 运行期间持续发送 typing action

Telegram 适配器 SHALL 在 `progress_func` 收到 `tool_call` 事件时，
调用 `sendChatAction(chat_id, "typing")`，利用 Telegram 平台原生打字指示器反馈状态。

#### Scenario: 工具调用触发 typing action

- **WHEN** `progress_func` 收到 `{"type": "tool_call", "name": "<any>"}` 事件
- **THEN** 向当前 chat_id 发送 `sendChatAction("typing")`
- **AND** Telegram 客户端展示"正在输入…"指示器（有效期约 5 秒）

#### Scenario: sendChatAction 失败时不中断 run

- **WHEN** `sendChatAction` 调用失败（网络错误或超时）
- **THEN** 异常被捕获并 log，agent run 继续，不影响最终回复
