## Why

#4a 把 IM 连接下沉 node 后，**入站 + 同步回复**已通，但**异步/带外出站在 managed 下断了**：agent 进程经 `connector_registry.snapshot(agent_name)`（agent_app.py:422 `connectors_resolver`）拿 connector，而 managed 下连接注册在 **node**、agent 进程的 registry 是**空的**。受影响：
- `permission_gate` 审批 DM（经 `outbound_connectors`，permission_gate.py:29/39-41）
- agent 侧 cron 触发的主动外发（`cron_scheduler._fire` 的 connector 快照）
- loop 里 `send_im_message` 等出站工具

这些都是 agent 主动外发、发生在 inbound turn 之外（或不依赖入站响应通道），#4a 的"同步回复经转发响应返回"覆盖不到它们。

> 车道 D #4b（IM-edge 出站，对称于 #4a 入站）。依赖 #4a(已落地，`node/im_edge.py` + 连接在 node)。沿用 openclaw delivery-queue 范式 + "node 读本机 agent 产物"（解耦安全）。

## What Changes

- **出站 delivery-queue**：agent_state.db 新增 `im_outbound_queue` 表（embedded-Y 迁移）——agent 把出站意图（platform、conversation address、text/payload、dedup_key、status、created_at）写入。
- **node drain**：node 的 IM-edge（`node/im_edge.py`）周期 drain 本机 agent 的 `im_outbound_queue`（读本地文件，非 RPC）→ 经其持有的 connector 发出 → 标记 sent。
- **agent 出站 emitter 改 mode-aware**：`connectors_resolver` / 出站发射点——**managed**（连接在 node）写队列；**standalone**（连接在 agent 进程）维持现行 `connector_registry.snapshot` 进程内直发。这条覆盖 permission_gate 审批 DM + cron 外发 + send_im_message 工具（它们都经同一出站抽象）。
- **投递语义**：at-least-once + `dedup_key`（node drain 用 dedup_key 防重发）；sent 行定期清理。审批 DM 宁可能重发也不丢。

### 不在本切片
- 同步回复（#4a 已做）；per-tenant IdP / 域映射；#5 `/link`。

## Capabilities

### Modified Capabilities
- `platform-agent-gateway`: 新增"node 经 delivery-queue 处理 agent 异步出站"——agent 写本机 `im_outbound_queue`，node drain 本机队列经其 connector 发出（at-least-once + dedup）；managed 下 agent 异步出站（审批 DM / cron / send_im_message）经队列、不依赖 agent 进程内 connector；standalone 维持进程内直发。

## Impact

- **owning packages**：`runtime`（`agent_app` connectors_resolver/出站发射点 mode-aware + 写队列）、`node`（`im_edge.py` drain 本机队列发出）、`im_gateway`（出站 emitter 抽象）、`governance`（permission_gate 经同一出站抽象，随之走队列；其本身用 outbound_connectors 抽象、改 resolver 即覆盖）、`cron_scheduler`（fire 出站走队列）
- **public API surface**：出站 emitter 契约（managed=队列写 / standalone=直发）；node drain
- **owned tables**：`agent_state.db` 新增 `im_outbound_queue`（**embedded-Y 迁移**，per-agent；**非 alembic → 不撞管理库迁移号**）
- **config namespace**：无（drain 间隔可复用 node 轮询配置）
- **cross-module dependencies**：node 读本机 agent `im_outbound_queue`（本地文件，"读 agent 产物"）；agent 只写自己侧队列；**无 agent→platform**；im_gateway 仍不 import platform
- **migration / shim**：agent_state embedded-Y 迁移（加 `im_outbound_queue`）；standalone 路径保留进程内直发
- **验证基线**：standalone 下异步出站仍进程内直发、`fleetent agent run` IM 不变
- 与在飞的 KB④ 零重叠（本 change 碰 runtime/node/im_gateway/governance；KB④ 碰 knowledge_base/kb_admin_api）
