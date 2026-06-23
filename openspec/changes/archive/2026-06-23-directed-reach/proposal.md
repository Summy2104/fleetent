## Why

agent 需要**主动按内部 `user_id` 触达用户**（用户不在对话里、地址未预配），首个需求是车道 A 的 **A4b**：reflection 的 user-memory 维护提案要送**本人**审批（A4a 已把它路由到 `reflection_user_memory_proposal`，但"送到本人"的投递一直缺）。

当前"找人"两个寻址模型都绕开了这件事——M1 在 agent.yaml 写死 approver 地址、M2 回发起者对话——**从不需要 `user_id → 渠道地址`的反向解析**。directed-reach 第一次补上它。设计权威见 `docs/architecture/directed-reach.md`。

合为一个 change（doc 切片 1-3）：原语、agent intent、A4b 接入彼此非独立可发布（原语单独落地=死代码），拆开只制造 churn。切片 4（降噪）deferred。

## What Changes

- **平台反向解析端点**：`POST /nodes/{node_id}/identity/addresses`（node-key 认证，镜像现有 `/identity/resolve`），入参 `user_id`（+tenant），出参该用户在 `im_users` 的全部 `[(platform, platform_user_id)]`。底层 `im_gateway_management.resolve_user_addresses(user_id)` 查 `im_users WHERE user_id=X`。
- **node 反向 client + drain 处理**：`node/im_edge.py` 加 `PlatformAddressResolver`（仿 `PlatformIdentityResolver`，调上面端点）；出站 drain 遇到 **user_id-目标意图**时反查地址 → **全发**到该用户所有绑定渠道（fan-out，逐地址投递）。无绑定 → 不投递 + 日志（提案留 pending）。
- **agent 侧 intent 出口**：`notify_user(user_id, message, *, blocks=None)` —— managed 下经 `outbound_connectors` 入队一条 **user_id-目标**意图到 `im_outbound_queue`（`address_json` 载 `{"target_type":"user_id","user_id":X}`，复用 JSON blob、**无 schema 改动**）；dev `agent run`（非 node-managed）无 node/绑定表 → 降级 no-op + 日志。
- **A4b 接入**：reflection 的 user-memory 提案通知改走 directed-reach `notify_user(proposal.user_id, <审批提示含 approve/reject id>)`，取代 A4a 占位的"配置 approver 地址"路径。回复经**既有审批链**（入站 resolver + `approve <id>` 关联回 `memory_proposal` 审批请求）——不新建回复通路。

**明确不做（切片 4 / deferred）**：per-agent 平台优先序降噪、可达性送达指标。"最近用"渠道（`im_users` 无 `last_seen`，不便宜）不做。

## Capabilities

### New Capabilities
- `directed-reach`: 按内部 user_id 主动触达——平台反向解析 + node fan-out 投递 + agent intent 出口；A4b（reflection user-memory 提案送本人）为首消费者。

### Modified Capabilities
（无；A4b 的审批回复关联复用既有 `approval-request-lifecycle`，本 change 不改其 spec。）

## Impact

- **owning package**：`platform/node_management`（反向端点）+ `platform/im_gateway_management`（`resolve_user_addresses` 查 im_users）、`node/im_edge`（反向 client + drain fan-out）、`outbound_connectors`（agent 入队 user_id 意图）、`runtime`（`notify_user` intent）、`reflection`（A4b 接入）
- **public API surface**：`notify_user(user_id, message)`（agent intent）；`im_gateway_management.resolve_user_addresses(user_id)`；`POST /nodes/{id}/identity/addresses`（node-key）；node `PlatformAddressResolver`
- **owned tables**：读 `im_users`（既有）；写 `im_outbound_queue`（既有，`address_json` 载 user_id-目标、**无 schema 改动**）。**无迁移**。
- **config namespace**：无新增
- **cross-module dependencies**：agent → `im_outbound_queue`（agent 侧队列）→ node drain → 平台反向端点（node-key）。**agent 不直接调 platform**（node 中介反查）——守 agent↔platform 解耦铁律。
- **migration / shim**：无迁移、无 schema 改动
- **受影响代码**：`src/fleetent/platform/node_management/node_desired_state_api.py`、`src/fleetent/platform/im_gateway_management/identity.py`、`src/fleetent/node/im_edge.py`、`src/fleetent/outbound_connectors.py`、`src/fleetent/runtime/`（notify_user 出口）、`src/fleetent/reflection/reflection.py` + 相关单测/集成测试
