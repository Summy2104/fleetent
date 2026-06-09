## MODIFIED Requirements

### Requirement: Slack 适配器经 Assistant 协议在正确线程展示进度

Slack 适配器 SHALL 遵循 Slack Agents & Assistants 协议处理 assistant 会话：
从 `assistant_thread_started`（例如经 slack-bolt 的 `Assistant` 容器）获取 assistant 线程的
真实 `channel_id` + `thread_ts`，并以该 `thread_ts` 调用 `set_status`，
使状态指示器渲染到用户所在的 Assistant 面板。状态文案 SHALL 反映当前批次的**全部**在途工具
（聚合），而非只显示其中一个。设置状态时 SHALL 同时提供 `loading_messages`，内容为当前批次的
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
- **THEN** 以 assistant 线程 `thread_ts` 调用 `set_status`，`status` 聚合展示两个工具的可读描述
- **AND** 同时传 `loading_messages`，其内容为该批**每个**工具的可读文案（如 `["📅 正在查询日历...", "📂 正在操作 Google Drive..."]`）
- **AND** 不出现「只显示最后一个工具」或消息区落到 Slack 内置默认占位的现象

#### Scenario: agent 完成后清除状态并发送回复

- **WHEN** agent run 完成，`reply_func` 被调用且状态可用
- **THEN** 先以 assistant 线程 `thread_ts` 调用 `set_status(status="")` 清除状态
- **AND** 通过 `say()` 将最终回复发送到该 assistant 线程

#### Scenario: 未启用 Assistants 功能时降级

- **WHEN** App 未开启 Agents & Assistants（`thread_started` 不触发或首次 `set_status` 失败）
- **THEN** 记 warning 并标记状态不可用，后续 progress 更新与清除均跳过
- **AND** agent run 正常进行，`reply_func` 仍通过 `say()` 发送最终回复，DM 对话可用

#### Scenario: 状态更新失败不中断 run

- **WHEN** 工具调用期间某次 `set_status` 更新抛异常
- **THEN** 异常被捕获并 log，agent run 继续，不因状态更新失败而中断

#### Scenario: 频道 @mention 路径保留

- **WHEN** 用户在频道中 @mention bot
- **THEN** 该消息经 `app_mention` 路径处理（不要求 assistant 状态指示器）
- **AND** assistant 容器仅接管 assistant 面板 / DM 会话，二者不重复响应同一条消息
