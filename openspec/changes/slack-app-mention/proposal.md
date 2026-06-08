## Why

当前 Slack adapter 注册的是 `message` 事件，bot 会响应它所在频道的**所有消息**，不需要 @mention。这在群频道中会造成干扰——频道里任何人发的任何消息都会触发 bot 回复。标准的 Slack bot 行为是：频道消息必须 @mention 才响应，DM 则直接响应无需 mention。

## What Changes

- **`im_gateway/slack.py`**：`create_app()` 中将事件处理逻辑提取为内部 `_handle()` 函数，注册两个独立事件处理器：
  - `app_mention`：处理频道 @mention
  - `message`（仅 `channel_type == "im"`）：处理 DM 私聊
  - 普通频道消息（非 @mention）不再触发 bot

## Capabilities

### New Capabilities

_无_

### Modified Capabilities

- `per-agent-slack-connector`：Slack adapter 的事件响应行为变更——频道消息改为只响应 @mention，DM 保持全量响应

## Impact

- `src/fleetent/im_gateway/slack.py`：`create_app()` 函数重构
- `tests/unit/test_slack_per_agent.py`：更新测试以覆盖 `app_mention` 和 DM-only `message` 两个处理器
- **Slack 应用配置**：需要在 api.slack.com 的 Event Subscriptions 中开启 `app_mention` 事件
