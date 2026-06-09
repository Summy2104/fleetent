## MODIFIED Requirements

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
