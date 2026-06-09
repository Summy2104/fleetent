## Why

Slack 适配器原先靠"发一条占位消息 + 反复 `chat.update`"展示进度,有两个问题:(1) 占位消息是线程里一条独立可见消息,完成后被最终回复替换,体验割裂;(2) 实测 `chat_postMessage` 返回的 `SlackResponse` 不是 `dict`,`isinstance(resp, dict)` 永远 False,占位 ts 取不到,进度反馈实际从未生效,一直走降级路径。

Slack 的 Agents & Assistants 功能提供原生状态指示器(`assistants.threads.setStatus`),显示在 bot 名下方、不占消息位、完成自动消失——正是 IM 进度反馈应有的形态。

## What Changes

- **修改** Slack 适配器:用 `assistant_threads_setStatus` 替代"占位消息 + chat.update"方案
  - 收到消息 → 设状态 "🤔 思考中..."
  - 每次工具调用 → 更新为该工具的可读中文状态(如 "📂 正在操作 Google Drive...")
  - 完成 → 清空状态,`say()` 发送最终回复
- **新增** 工具名 → 可读中文状态的映射 `_TOOL_STATUS` + `_tool_status_text()` fallback
- 未启用 Agents & Assistants 功能的 App 自动降级为纯 `say()` 回复(无状态)
- **不改** `progress_func` 管线、Telegram typing action 等其余 `im-progress-feedback` 行为

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `im-progress-feedback`: Slack 进度反馈机制从"占位消息 + chat.update"改为原生 Assistants API 状态指示器;`progress_func` 管线、Telegram 行为不变

## Impact

- `src/fleetent/im_gateway/slack.py`:`_handle()` 重写状态反馈逻辑,新增 `_TOOL_STATUS` / `_tool_status_text()`
- `tests/unit/`:新增 Slack 状态指示器测试
- 无新依赖(`assistant_threads_setStatus` 在已装的 slack-sdk 3.42 中)
- 前置条件:Slack App 需开启 Agents & Assistants 功能(未开启则自动降级)
