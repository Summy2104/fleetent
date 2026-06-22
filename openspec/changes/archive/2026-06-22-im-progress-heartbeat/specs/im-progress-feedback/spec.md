## ADDED Requirements

### Requirement: 顶层 run 期间发出时间驱动心跳事件

`agent_loop._run_inner()` MUST 在顶层 run(`is_sub_agent` 为假且 `progress_func` 非 None)期间启动一个**时间驱动的心跳**：每隔一个可注入的间隔(模块级常量，约 4 秒)，以 `progress_func({"type": "heartbeat", "elapsed_s": N})` 调用一次，其中 `elapsed_s` 为自该 run 开始的整数秒。心跳事件 MUST 仅含 `type` 与 `elapsed_s`，不含工具参数或任何敏感信息。心跳为**时间驱动**，与是否有工具在执行无关——因此在长 LLM 调用、单个长工具、整个 sub_agent 执行等无 `tool_call` 事件的区间也持续发出。`progress_func` 为 None 时 MUST 不启动心跳，行为与未引入心跳时完全一致。

#### Scenario: 静默区间持续发心跳

- **WHEN** 顶层 run 传入非 None 的 `progress_func`，且某段时间内没有新的工具批次(长 LLM 调用 / 单个长工具执行中)
- **THEN** 心跳按间隔持续以 `{"type":"heartbeat","elapsed_s":N}` 调用 `progress_func`，`elapsed_s` 随时间递增

#### Scenario: 心跳事件不含敏感信息

- **WHEN** 心跳事件被发出
- **THEN** 事件 dict 仅含 `type`(值为 `"heartbeat"`)与 `elapsed_s`，不含工具参数或任何敏感字段

#### Scenario: 无 progress_func 时不启动心跳

- **WHEN** 顶层 run 的 `progress_func` 为 None
- **THEN** 不创建任何心跳 task，run 行为与未引入心跳时完全一致

### Requirement: sub_agent 不启动独立心跳

sub_agent 运行(`is_sub_agent` 为真)MUST NOT 启动自己的心跳；顶层 run 的心跳在 sub_agent 执行期间持续发出即已覆盖其墙钟。该要求与既有「sub_agent 内工具调用不触发父 `progress_func`」不冲突：心跳是顶层 run 的时间驱动行为，不是 sub_agent 的工具事件。

#### Scenario: sub_agent 执行期间由父心跳保活

- **WHEN** 顶层 run 调用 sub_agent，sub_agent 内部长时间执行
- **THEN** 顶层 run 的心跳在此期间持续发出 `heartbeat` 事件，而 sub_agent 自身不启动心跳、其内部工具不触发父 `progress_func`

### Requirement: 心跳 task 遵守 owner-task 生命周期且舱壁化

心跳 task MUST 在启动它的同一协程内创建并取消(owner-task 契约)：run 结束(正常或异常)时 MUST `cancel()` 该 task 并吞掉 `CancelledError`，不泄漏、不跨 task 取消。心跳循环 MUST 舱壁化——`progress_func` 在心跳中抛出的异常 MUST 被捕获并记日志，MUST NOT 中断 run、MUST NOT 改变 run 的返回值或进程退出码。

#### Scenario: run 结束时心跳被取消

- **WHEN** 顶层 run 正常返回或抛出异常
- **THEN** 心跳 task 在同一协程的 finally 中被 `cancel()` 并完成清理，不残留运行中的心跳 task

#### Scenario: 心跳中 progress_func 抛错不影响 run

- **WHEN** 心跳调用 `progress_func` 时抛出异常(如网络错误)
- **THEN** 异常被捕获并 log，心跳继续按间隔尝试，run 正常进行且返回值/退出码不受影响

### Requirement: Slack 心跳保活并显示已耗时

Slack 适配器 MUST 处理 `heartbeat` 事件：记住最近一次**非心跳**(`tool_call`)事件设置的状态文案(初始为「🤔 思考中...」)，收到 `heartbeat` 时以「`<最近文案> · 已 {elapsed_s}s`」重新调用 `set_status`(并提供对应 `loading_messages`)。心跳与 `tool_call` 事件 MUST NOT 互相把对方的状态清空。

#### Scenario: 心跳重发保活并追加耗时

- **WHEN** Slack 适配器先收到某批工具的 `tool_call` 事件、随后收到 `heartbeat(elapsed_s=45)`
- **THEN** `set_status` 被以「该批工具文案 · 已 45s」重新调用，使状态指示器保活且可见地反映已耗时

#### Scenario: 无工具时心跳仍保活

- **WHEN** 尚无任何 `tool_call` 事件即收到 `heartbeat`
- **THEN** 以「🤔 思考中... · 已 Ns」调用 `set_status`，状态指示器保持存在

### Requirement: Telegram 心跳重发 typing

Telegram 适配器 MUST 对 `heartbeat` 事件同样发出 `send_chat_action("typing")`，使约 5 秒过期的 typing 指示器被周期性 re-arm、在长任务期间持续可见。

#### Scenario: 心跳 re-arm typing

- **WHEN** Telegram 适配器收到 `heartbeat` 事件
- **THEN** 调用 `send_chat_action(action="typing")`，刷新 typing 指示器的 5 秒窗口
