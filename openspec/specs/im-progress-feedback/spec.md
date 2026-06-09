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

### Requirement: Slack 适配器使用 Assistants API 状态指示器展示进度

Slack 适配器 SHALL 在 agent 运行期间通过 Slack Agents & Assistants 的 `assistant_threads_setStatus` 展示原生状态指示器(显示在 bot 名下方,不占消息位,完成后清除),而非发送占位消息。状态文案 SHALL 在工具调用时更新为该工具的可读中文描述。未启用该功能的 App SHALL 平滑降级为纯 `say()` 回复。

#### Scenario: 消息到达时设置初始状态

- **WHEN** Slack `_handle()` 收到用户消息
- **THEN** 调用 `assistant_threads_setStatus(channel_id, thread_ts, status="🤔 思考中...")`
- **AND** 成功则标记状态可用,失败则记 warning 并标记降级

#### Scenario: 工具调用时更新为可读中文状态

- **WHEN** `progress_func` 收到 `{"type": "tool_call", "name": "google-workspace__manage_drive"}` 事件且状态可用
- **THEN** 调用 `setStatus` 将状态更新为可读文案(如 "📂 正在操作 Google Drive...")
- **AND** 未命中映射的工具名通过前缀匹配或去命名空间 fallback 生成合理文案

#### Scenario: agent 完成后清除状态并发送回复

- **WHEN** agent run 完成,`reply_func` 被调用且状态可用
- **THEN** 先调用 `setStatus(status="")` 清除状态指示器
- **AND** 通过 `say()` 发送最终回复到目标 thread

#### Scenario: 未启用 Assistants 功能时降级

- **WHEN** 首次 `setStatus` 调用失败(App 未开启 Agents & Assistants 功能)
- **THEN** 记 warning 并标记状态不可用,后续 progress 更新与清除均跳过
- **AND** agent run 正常进行,`reply_func` 仍通过 `say()` 发送最终回复

#### Scenario: 状态更新失败不中断 run

- **WHEN** 工具调用期间某次 `setStatus` 更新抛异常
- **THEN** 异常被捕获并 log,agent run 继续,不因状态更新失败而中断

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
