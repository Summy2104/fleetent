# im-channel-allowlist Delta

## REMOVED Requirements

### Requirement: Channel allowlist storage
**Reason**: `im_channel_allowlist` 表 descope——渠道准入已由 IM 访问模型的 `im.<platform>.allow_groups`（群白名单）+ chat_type 闸接管，本表 runtime 从不消费（`is_allowed` 零生产调用方）。

### Requirement: Per-platform opt-in enforcement
**Reason**: 其开关 `im_connectors.allowlist_enforced` 专为 gate 本 allowlist，随表移除。

### Requirement: Routing enforces the channel allowlist before the agent pipeline
**Reason**: 准入强制改由 agent.yaml `im.allow_groups` + 闸；旧的渠道白名单路由强制已死（`is_allowed` 无调用）。

### Requirement: Allowlist management surface
**Reason**: 表移除后无对象可配；`/allowlist` admin 端点 + CLI 一并删除。渠道准入配置改为配 agent 的 `agent_im_groups` 群白名单（IM 访问模型）。
