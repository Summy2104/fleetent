## Why

Slack Assistant 面板里,底部状态栏(`assistant_threads_setStatus` 的 `status`)已正确显示 fleetent 设置的 per-tool emoji 状态(如「📅 正在查询日历 · 📂 正在操作 Google Drive…」),但**消息区的轮播占位**仍在循环显示 Slack 的**内置默认文案**(「整体梳理中…」「处理中…」)。根因:fleetent 只设了 `status`,没传 `loading_messages` 参数,Slack 遂用它自己的本地化默认 loading 文案填充消息区轮播。这与已修正的状态栏不一致,观感上仍像「内置内容在循环」。

## What Changes

- **Slack 适配器在 Assistant 路径调用 `set_status` 时一并传 `loading_messages`**,内容**镜像当前批次的逐工具可读文案**(如 `["📅 正在查询日历...", "📂 正在操作 Google Drive..."]`),使消息区轮播展示 fleetent 的工具文案而非 Slack 默认占位。
- 初始(首个工具前)阶段同样传我们的 loading 文案(如「🤔 思考中...」),避免 Slack 默认占位先行出现。
- 仅影响 Assistant 路径(`set_status` 工具);channel `app_mention` / 非-assistant DM fallback 不涉及(无消息区轮播)。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `im-progress-feedback`: Slack 进度展示在设置 assistant 状态时,SHALL 同时提供 `loading_messages`(镜像当前批次工具文案),使消息区轮播展示 fleetent 文案而非 Slack 内置默认。

## Impact

- **代码**:`src/fleetent/im_gateway/slack.py`(`_route_assistant_message` 的 `set_status` 调用增传 `loading_messages`;新增一个 names→loading 文案列表的辅助)。
- **依赖**:无新增;slack-bolt 的 `set_status(status, loading_messages=...)` 已支持。
- **测试**:`tests/unit/test_slack_assistant.py` 增断言 set_status 收到 loading_messages。
- **架构约束**:仅 agent runtime(`im_gateway/`),不依赖 platform。
