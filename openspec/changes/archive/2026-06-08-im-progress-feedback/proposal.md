## Why

当用户通过 Slack / Telegram 向 agent 发送消息后，bot 在整个处理过程中保持沉默——
无论 agent 跑了多少轮工具调用，用户都看不到任何反馈，极易误以为 bot 已宕机或消息丢失。
此问题在工具密集型任务（搜索、代码执行、多步推理）中尤为突出，严重影响使用体验。

## What Changes

- **NormalizedMessage** 新增可选字段 `progress_func`：一个异步回调，供适配器在 agent
  运行期间持续接收进度事件（工具调用名称、运行状态），不影响现有只传 `reply_func` 的适配器
- **normalizer.route()** 内部从 `agent_loop.run()` 切换为 `agent_loop.run_stream()`，
  消费流式事件并在适当时机调用 `progress_func`；最终 `done` 事件触发 session 保存和 `reply_func`
- **Slack 适配器**：消息到达时立即 `postMessage` 一条占位消息（"🤔 思考中…"），
  随后通过 `progress_func` 接收事件，节流后用 `chat.update` 原地更新，完成后替换为最终回复
- **Telegram 适配器**：通过 `progress_func` 接收事件时定期调用 `sendChatAction("typing")`，
  Telegram 平台自动在 UI 展示打字中状态
- 工具进度展示**仅展示工具名称**，不暴露参数、输入内容或任何可能含敏感信息的字段

## Capabilities

### New Capabilities

- `im-progress-feedback`: IM 适配器实时进度反馈——NormalizedMessage progress_func 回调接口、
  normalizer 流式事件路由、Slack 占位消息节流更新、Telegram typing action 发送

### Modified Capabilities

- `im-gateway`: NormalizedMessage 契约新增可选 `progress_func` 字段；normalizer.route()
  内部改用 run_stream()，行为语义不变但增加进度通知路径

## Impact

- `src/fleetent/im_gateway/normalizer.py`：route() 切换为 run_stream()，增加 progress 事件分发逻辑
- `src/fleetent/im_gateway/slack.py`：handle_message() 构造 progress_func 闭包，
  调用 Slack Web API（chat.postMessage / chat.update）
- `src/fleetent/im_gateway/telegram.py`：handle_message() 构造 progress_func 闭包，
  调用 sendChatAction
- 新增 Slack Web API 客户端调用（需 `chat:write` scope，已有；无需新增权限）
- 无数据库变更，无 migration，无 API 契约变更（reply_func 语义不变）
- Telegram 和 Slack 以外的适配器（未来扩展）可不传 progress_func，降级为当前静默行为
