## Why

`AgentBindings` 在 IM 场景下已成死代码——per-agent connector 通过连接本身识别 agent，`by_channel`/`by_user` 路由永远不被调用。同时，顶层 `AgentAccess` 块对所有平台共用一套访问策略，而 Slack 与 Telegram 往往需要不同的访问规则（例如 Slack 用于内部团队，Telegram 面向外部用户）。

## What Changes

- **删除 `AgentBindings`**：从 `AgentFile` 移除 `bindings` 字段及 `AgentBindings` 类；从 `AgentConfigIndex` 移除 `by_channel`/`by_user` 路由表及 `agent_for_channel()`/`agent_for_user()` 方法；简化 `build_index()` 和 `runtime/snapshot.py`
- **引入 `ConnectorAccess`**：新建可复用的 `ConnectorAccess` pydantic 模型，包含 `allow_channels`、`allow_users`、`require_approval` 字段，作为 Slack 和 Telegram connector 的内嵌 access policy
- **将 `AgentAccess` 下沉到 connector**：`SlackConnector` 和 `TelegramConnector` 各自内嵌 `access: ConnectorAccess`，顶层 `AgentFile.access` 字段及 `AgentAccess` 类一并删除
- **更新运行时访问门控**：`normalizer.py` 按 `msg.platform` 读取对应 connector 的 `.access`；`im_gateway/access.py` 门控函数签名改为接受 `ConnectorAccess`
- **纯结构重构**：访问控制行为不变，只是配置读取路径从 `agent.access` 改为 `agent.connectors.<platform>.access`

## Capabilities

### New Capabilities

_无（纯结构重构，不引入新能力）_

### Modified Capabilities

- `per-agent-im-access`：access 配置的读取路径从 `AgentFile.access`（顶层）变更为各 connector 的内嵌 `access: ConnectorAccess`；`channel_allowed`/`user_allowed` 函数签名改为接受 `ConnectorAccess`
- `per-agent-slack-connector`：`SlackConnector` 新增内嵌 `access: ConnectorAccess` 字段，取代原 connector 层仅有 `channels` 过滤的设计；`connectors.slack.channels` 字段删除（频道过滤统一由 `access.allow_channels` 承担）
- `per-agent-telegram-connector`：同上，`TelegramConnector` 新增 `access: ConnectorAccess`，删除 `channels` 字段

## Impact

- `src/fleetent/agent_config.py`：删 `AgentBindings`、删 `AgentAccess`、删 `AgentFile.bindings/access`；新增 `ConnectorAccess`；`SlackConnector`/`TelegramConnector` 加 `access: ConnectorAccess`，删 `channels` 字段；`AgentConfigIndex` 删 `by_channel`/`by_user` 及相关方法；`build_index()` 简化
- `src/fleetent/im_gateway/access.py`：`channel_allowed()`/`user_allowed()` 接受 `ConnectorAccess`
- `src/fleetent/im_gateway/normalizer.py`：`get_agent_for_context()` 简化（仅返回 default agent）；access gate 按 platform 读 connector 的 `.access`
- `src/fleetent/runtime/snapshot.py`：移除 `agent_for_channel`/`agent_for_user` 引用
- `agents/default/agent.yaml.example`：更新 connectors 示例，移除顶层 `access` 块，改为各 connector 内嵌 `access:`
- 测试：更新所有涉及 `bindings`、`AgentAccess`、`access.channel_allowed/user_allowed` 参数签名的测试
