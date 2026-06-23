## Purpose

Provide real-time progress feedback to IM users during agent runs by propagating an optional
`progress_func` callback through the agent pipeline to IM adapters, enabling platform-native
indicators (e.g., Slack message updates, Telegram typing action) when tools are invoked.

## Requirements

### Requirement: NormalizedMessage 携带可选 progress_func 回调

`NormalizedMessage` SHALL 携带可选字段 `progress_func: Callable[[dict], Awaitable[None]] | None`，
默认值为 `None`。当为 `None` 时，所有行为与未引入进度反馈时完全一致，不引入任何副作用。
当被调用时，事件 dict SHALL 形如 `{"type": "tool_call", "names": [<tool_name>, ...]}`，
其中 `names` 为该轮**即将并行执行的全部工具名**列表；为向后兼容，事件 MAY 同时保留
`"name": names[0]`。事件 MUST 仅含 `type` / `names`（及兼容用的 `name`）字段，
不含工具参数或任何敏感信息。

#### Scenario: 不传 progress_func 时行为不变

- **WHEN** IM 适配器构造 `NormalizedMessage` 时未传 `progress_func`
- **THEN** normalizer.route() 执行与未引入进度反馈时完全相同，不产生任何进度事件

#### Scenario: 传入 progress_func 时，整批工具执行前被调用一次

- **WHEN** IM 适配器传入非 `None` 的 `progress_func`，agent 在某一轮发起一批共 K 个工具调用
- **THEN** 在该批工具实际执行前，`progress_func({"type": "tool_call", "names": [<K 个工具名>]})` 被 await **恰好一次**
- **AND** 事件 dict 仅含 `type` / `names`（及兼容用 `name=names[0]`），不含工具参数或任何敏感信息

### Requirement: agent_loop.run() 透传 progress_func 到工具调度层

`agent_loop.run()` 和内部 `_run_inner()` SHALL 接受 `progress_func` 参数，
并在确定本轮**待执行工具批次**的全部工具名后、该批**实际执行前**，
以一次 `{"type": "tool_call", "names": [...]}` 事件调用之。
guardrail 判定与（medium/high）风险审批 MUST 仍按原 `tool_calls` 顺序串行决策，
不受进度发出方式影响。

#### Scenario: 批次执行前触发一次聚合 progress 事件

- **WHEN** `run()` 收到非 `None` 的 `progress_func`，agent loop 某一轮决定并行调用 `google-workspace__manage_calendar` 与 `google-workspace__manage_drive`
- **THEN** 在两工具实际执行前，`progress_func({"type": "tool_call", "names": ["google-workspace__manage_calendar", "google-workspace__manage_drive"]})` 被 await 一次
- **AND** 进度不再对每个工具在规划阶段毫秒级连发、互相覆盖

#### Scenario: progress_func 异常不中断 agent run

- **WHEN** `progress_func` 调用时抛出异常（如网络错误）
- **THEN** 异常被捕获并 log，agent run 继续正常执行，不因 progress 失败而中断

#### Scenario: 决策阶段保持串行

- **WHEN** 主循环处理一轮多个 `tool_calls`
- **THEN** 每个工具的 guardrail 判定与（medium/high）风险审批按原 `tool_calls` 顺序串行进行，仅进度以一次批级事件发出

#### Scenario: sub_agent 内工具调用不触发父 progress_func

- **WHEN** agent run 中包含 sub_agent 调用，sub_agent 内部执行工具
- **THEN** 仅顶层 agent 的工具批次触发 `progress_func`，sub_agent 的工具调用不触发

### Requirement: Slack 适配器经 Assistant 协议在正确线程展示进度

Slack 适配器 SHALL 遵循 Slack Agents & Assistants 协议处理 assistant 会话：
从 `assistant_thread_started`（例如经 slack-bolt 的 `Assistant` 容器）获取 assistant 线程的
真实 `channel_id` + `thread_ts`，并以该 `thread_ts` 调用 `set_status`，
使状态指示器渲染到用户所在的 Assistant 面板。状态文案 SHALL 反映当前批次的**全部**在途工具
（聚合），而非只显示其中一个。**所有设置 Slack 状态的路径**（assistant 路径与频道 `app_mention` /
非-assistant DM 的 fallback 路径）SHALL 在设置状态时同时提供 `loading_messages`，内容为当前批次的
**逐工具可读文案**（初始/无工具时为「🤔 思考中...」），使 Slack 消息区轮播展示 fleetent 的文案
而非 Slack 内置默认占位。未启用 Agents & Assistants 的 App SHALL 平滑降级为纯 `say()` 回复。
频道 `app_mention` 路径 SHALL 保留。

#### Scenario: 从 assistant 线程获取正确的 thread_ts

- **WHEN** 用户在 Assistant 面板中向 bot 发消息
- **THEN** 适配器从 `assistant_thread_started` / `Assistant` 容器获得该 assistant 线程的 `channel_id` 与 `thread_ts`
- **AND** 后续 `set_status` / 最终回复 / 图片上传均绑定到该 `thread_ts`，而非消息自身的 `event.ts`

#### Scenario: 消息到达时设置初始状态到正确线程

- **WHEN** assistant `user_message` 处理器收到用户消息
- **THEN** 以 assistant 线程的 `thread_ts` 调用 `set_status(status="🤔 思考中...")`
- **AND** 同时传 `loading_messages=["🤔 思考中..."]`，使消息区轮播不落到 Slack 默认占位
- **AND** 成功则标记状态可用，失败则记 warning 并标记降级

#### Scenario: 批次工具调用时聚合展示并镜像 loading_messages

- **WHEN** `progress_func` 收到 `{"type": "tool_call", "names": ["google-workspace__manage_calendar", "google-workspace__manage_drive"]}` 且状态可用
- **THEN** 调用 `set_status`，`status` 聚合展示两个工具的可读描述
- **AND** 同时传 `loading_messages`，其内容为该批**每个**工具的可读文案（如 `["📅 正在查询日历...", "📂 正在操作 Google Drive..."]`）
- **AND** 不出现「只显示最后一个工具」或消息区落到 Slack 内置默认占位的现象

#### Scenario: 频道 @mention 路径也提供 loading_messages

- **WHEN** 用户在频道中 @mention bot，agent 经 fallback 路径（`_make_status_funcs`）展示进度
- **THEN** 该路径的初始状态与每次 progress 更新均同时提供 `loading_messages`（初始为「🤔 思考中...」，工具批次为逐工具文案）
- **AND** 频道消息区轮播展示 fleetent 文案，而非 Slack 内置默认占位

#### Scenario: agent 完成后清除状态并发送回复

- **WHEN** agent run 完成，`reply_func` 被调用且状态可用
- **THEN** 先调用 `set_status(status="")` 清除状态
- **AND** 通过 `say()` 将最终回复发送到目标 thread

#### Scenario: 未启用 Assistants 功能时降级

- **WHEN** App 未开启 Agents & Assistants（`thread_started` 不触发或首次 `set_status` 失败）
- **THEN** 记 warning 并标记状态不可用，后续 progress 更新与清除均跳过
- **AND** agent run 正常进行，`reply_func` 仍通过 `say()` 发送最终回复，DM 对话可用

#### Scenario: 状态更新失败不中断 run

- **WHEN** 工具调用期间某次 `set_status` 更新抛异常
- **THEN** 异常被捕获并 log，agent run 继续，不因状态更新失败而中断

#### Scenario: 频道 @mention 路径保留

- **WHEN** 用户在频道中 @mention bot
- **THEN** 该消息经 `app_mention` 路径处理
- **AND** assistant 容器仅接管 assistant 面板 / DM 会话，二者不重复响应同一条消息

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

### Requirement: 顶层 run 期间发出时间驱动心跳事件

`agent_loop.run()`（包裹 _run_inner 的顶层 run 路径）MUST 在顶层 run(`is_sub_agent` 为假且 `progress_func` 非 None)期间启动一个**时间驱动的心跳**：每隔一个可注入的间隔(模块级常量，约 4 秒)，以 `progress_func({"type": "heartbeat", "elapsed_s": N})` 调用一次，其中 `elapsed_s` 为自该 run 开始的整数秒。心跳事件 MUST 仅含 `type` 与 `elapsed_s`，不含工具参数或任何敏感信息。心跳为**时间驱动**，与是否有工具在执行无关——因此在长 LLM 调用、单个长工具、整个 sub_agent 执行等无 `tool_call` 事件的区间也持续发出。`progress_func` 为 None 时 MUST 不启动心跳，行为与未引入心跳时完全一致。

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
