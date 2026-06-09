## Why

上一个 change(slack-assistant-loading-messages)给 Slack 状态补了 `loading_messages`,但**只覆盖了 assistant 路径**(`_route_assistant_message`);**频道 `app_mention` 走的 `_make_status_funcs` fallback 路径被遗漏**。结果:频道里 @mention bot 时,消息区轮播仍显示 Slack 内置默认占位(「整体梳理中…」),与 DM 面板不一致。这是上个 change spec(「设置状态时 SHALL 同时提供 loading_messages」)的实现遗漏。

## What Changes

- **`_make_status_funcs`(频道/非-assistant fallback 路径)的两处 `assistant_threads_setStatus` 调用补 `loading_messages`**:初始传 `["🤔 思考中..."]`,progress 传当前批次逐工具文案(复用 `_loading_messages_for_event`)。
- 与 assistant 路径行为对称,频道消息区轮播展示 fleetent 文案而非 Slack 默认。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `im-progress-feedback`: 明确 Slack 进度展示在**所有路径**(含频道 `app_mention` fallback)设置状态时均 SHALL 提供 `loading_messages`,使消息区轮播展示 fleetent 文案。

## Impact

- **代码**:`src/fleetent/im_gateway/slack.py`(`_make_status_funcs` 两处 setStatus 增传 `loading_messages`)。
- **依赖**:无;raw `assistant_threads_setStatus` 已支持 `loading_messages`。
- **测试**:`tests/unit/test_slack_status.py` 增断言。
- **架构**:仅 agent runtime,不依赖 platform。
