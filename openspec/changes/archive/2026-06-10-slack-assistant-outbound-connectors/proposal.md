## Why

Slack **Assistant 面板路径**（`_route_assistant_message`）构造 `NormalizedMessage` 时漏填 `outbound_connectors`，而普通 DM/频道路径（`_handle`）有填。后果：assistant-pane 会话里 ① `send_im_message` 报「无可用 slack 连接器」（用户实测命中，2026-06-10 晚）；② 审批门无法外呼审批人（预存缺口，被新工具暴露）。违反 `builtin-outbound-tool` spec 的「Slack 会话中可经注入连接器发送」。

## What Changes

- `_route_assistant_message` 的 `NormalizedMessage` 补 `outbound_connectors={"slack": client}`（client 已在作用域内，与 `_handle` 路径对齐）

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `builtin-outbound-tool`: 「DM sent to a third-party user」requirement 增补 assistant-pane 场景（两条 Slack 入站路径均注入连接器）

## Impact

- **代码**：`im_gateway/slack.py` 单行 + 单元测试
- **不改**：channel 路径、Telegram、工具与 gate 本体
