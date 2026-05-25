## Why

IM 用户可以无限制地与 bot 交互，存在越权风险。同时，agent 目前只能按用户维度绑定，群聊场景下无法为整个 channel 指定 agent，功能不完整。

## What Changes

- `im_users` 表新增 `allowed` 字段（默认 `False`），新用户自动注册后需管理员审批才能使用 bot
- `normalizer.py` 新增准入检查：`allowed=False` 的用户直接收到拒绝提示，不进入 agent 流程
- `im_user_store.py` 改为 `get_or_create` 语义，但新用户默认 `allowed=False`
- 新增 `channel_agents` 表，支持按 `(platform, channel_id)` 绑定 agent
- `agent_store.py` 新增默认 agent 查找（`get_default_agent()`），由 `Settings.default_agent_name` 控制
- `normalizer.py` agent 查找顺序升级为：channel → user → default → 裸跑
- `admin.py` 扩展：`list-pending`、`approve-user`、`block-user`、`set-default-agent`、`assign-channel`、`unassign-channel`

## Capabilities

### New Capabilities

- `im-user-allowlist`: IM 用户准入控制——注册后默认待审批，管理员通过 CLI 审批/拒绝用户
- `channel-agent-binding`: 按 platform + channel_id 绑定 agent，优先级高于用户绑定
- `default-agent`: 全局默认 agent 配置，未绑定用户/channel 时的兜底

### Modified Capabilities

- `im-user-mapping`: 新增 `allowed` 字段和准入语义，改变 unknown user 的处理行为

## Impact

- `src/fleetent/im_user_store.py` — 新增 `allowed` 字段，新增 `approve_user()`、`block_user()`、`list_pending()`
- `src/fleetent/agent_store.py` — 新增 `channel_agents` 表 CRUD，新增 `get_default_agent()`、`get_agent_for_channel()`
- `src/fleetent/config.py` — 新增 `default_agent_name: str | None`
- `src/fleetent/im_gateway/normalizer.py` — 新增准入检查 + 更新 agent 查找顺序
- `src/fleetent/admin.py` — 新增 6 条 CLI 命令
- `tests/` — 对应新增单元测试
