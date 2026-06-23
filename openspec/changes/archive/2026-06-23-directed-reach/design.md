## Context

grounding（2026-06-23，详见 `docs/architecture/directed-reach.md`）：

- **出站脊柱**（#4b）：managed agent 经 `outbound_connectors.ManagedOutboundConnector.enqueue_text(target, ...)` 写 `im_outbound_queue`（`im_gateway/outbound_queue_store.enqueue(platform, address, payload, dedup_key)`，`address_json`/`payload_json` 是 JSON blob）。`is_node_managed_runtime()`（env FLEETENT_NODE_ID/PLATFORM_URL/SERVICE_KEY）判 managed；standalone 直发 live connector。
- **node drain**：`node/im_edge.py` 后台任务 drain agent 侧队列、用 node 自己的 connector 投递。
- **node→平台 client 范式**：`im_edge.PlatformIdentityResolver` 调 `POST /nodes/{node_id}/identity/resolve`（`Authorization: Bearer {service_key}`）做**入站**身份解析（渠道→user）。
- **平台端点范式**：`node_desired_state_api.py:125 post_identity_resolve`（`_authenticate_node` 依赖、入 channel+platform_user_id、出 user_id）。
- **绑定表**：`im_users(platform, platform_user_id, user_id, created_at, meta_json)`，UNIQUE(platform, platform_user_id)，**无 last_seen**。`WHERE user_id=X` 反查该用户全部渠道。
- **审批回复**：reflection user-memory 提案已建 `approval_requests`（subject_type=memory_proposal）；入站回复 `approve <id>` 经 approval_router 关联——**已具备**。

## Goals / Non-Goals

**Goals:** 通用 directed-reach 原语（agent 发 user_id 意图 → 平台/node 反查 + fan-out 投递）；A4b 接入送本人；守解耦（agent 不碰地址、不调 platform）；无迁移。

**Non-Goals:** 降噪/优先序/送达指标（切片 4）；"最近用"渠道；新回复通路（复用审批链）；改 tool_call 路由。

## Decisions

**D1 · 反查在 node drain 时做，不在 agent**。agent 入队一条 **user_id-目标**意图即返回；node drain 该意图时调平台反向端点解析地址 → fan-out 投递。理由：agent MUST NOT 调 platform（解耦铁律），node 是合法中介（已持 service key + 调 `/identity/resolve` 的范式）。**不**让 agent 先解析再入队。

**D2 · 平台反向端点 `POST /nodes/{node_id}/identity/addresses`**。`_authenticate_node` 认证，入 `{user_id, tenant_id}`，出 `{addresses: [{platform, platform_user_id}]}`。底层 `im_gateway_management.resolve_user_addresses(user_id)` 查 `im_users WHERE user_id=X`。镜像 `post_identity_resolve` 写法。

**D3 · user_id 意图复用 im_outbound_queue、无 schema 改动**。`address_json` 是 JSON blob → 载 `{"target_type":"user_id","user_id":X,"tenant_id":T}`（vs 现有 `{"target":..,"target_type":"user"}`）。node drain 按 `target_type` 分支：`"user"`→直发（现状）；`"user_id"`→反查+fan-out。agent 侧加 `outbound_connectors` 的 user_id 入队路径 + `notify_user(user_id, message)` 薄出口。

**D4 · fan-out = 全发所有绑定渠道**。反查得 N 个 (platform, address) → 逐个投递（node 用各 platform connector）。审批语义批准一次、resolve 去重，重复 DM 无害、最可达。`im_users` 无 last_seen 故不做"最近用"；优先序留切片 4。

**D5 · 不可达（无绑定）→ 不投递 + 日志**。反查返回空 → node 记日志、不投递；对应 A4b 提案保持 pending，等用户将来绑定渠道后下轮再触达。不回退兜底 approver（违"本人审批自己记忆"初衷）。

**D6 · standalone/dev 降级**。`is_node_managed_runtime()` false（无 node）→ `notify_user` no-op + 日志。directed-reach 只面向 managed（platform 始终在场），dev `agent run` 无 im_users 表、不为它设计绑定源。

**D7 · A4b 接入 + 回复复用**。reflection `_notify_pending_proposal`（或其等价点）对 user-memory 提案改调 `notify_user(proposal.user_id, <含 approve/reject {approval_id} 的提示>)`，取代 A4a 占位的 resolve_approvers 配置地址。owner 回复 `approve <id>` 经既有入站 resolver + approval_router 关联回 `memory_proposal` 审批——**零新增回复通路**。

## Risks / Trade-offs

- **跨三进程**（agent 入队 / node drain+反查 / platform 端点）：一个 change 跨边界，测试面含 unit（各段）+ integration（端点 + drain 分支）。但逻辑高度内聚，是一件事。
- **node drain 分支不可漏 standalone/无 node**：dev 路径 `notify_user` 必须 no-op、不抛——加测试覆盖"非 managed → no-op"。
- **fan-out 失败舱壁化**：单渠道投递失败只记日志、不影响该用户其它渠道、不中断 drain（参照既有出站 best-effort）。
- **A4b 切换 delivery**：user-memory 从 A4a 的"配置地址"切到 directed-reach(owner)。`reflection_user_memory_proposal` 配置 key 对 user-memory 不再用于投递（可留作 dormant，不强删）；shared/skill 仍走配置地址路径不变。需测试确认只改 user-memory 这一支、不动 shared/skill。
- **解耦护栏**：agent 侧只 import `outbound_connectors`/队列，绝不 import platform；反查端点调用发生在 node。`check_module_boundaries` 必须仍绿。
