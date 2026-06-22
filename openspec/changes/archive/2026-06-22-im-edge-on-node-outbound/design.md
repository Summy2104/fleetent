## Context

- #4a 落地：连接在 node（`node/im_edge.py`），入站 + 同步回复（经转发响应返回）已通。
- agent 出站经 `connector_registry.snapshot(agent_name)`：`agent_app.py:422` `connectors_resolver=lambda: connector_registry.snapshot(agent_name)`。managed 下 connector 注册在 node（slack.py:695/telegram.py:187 register 现跑在 node），agent 进程 registry **空** → 异步出站拿不到 connector。
- 受影响出站源：`governance/permission_gate.py`（审批 DM，经 `outbound_connectors`）、`cron_scheduler._fire(connectors)`（fire 出站快照）、loop 内 send_im_message 工具。
- agent_state.db 现有表见 agent_state_migrations.py（embedded-Y）。

## Goals / Non-Goals

**Goals:**
- managed 下 agent 异步出站经 delivery-queue → node drain → 发出；解耦安全（agent 只写自己侧、node 读本机产物）。
- standalone 维持进程内直发。
- at-least-once + dedup。

**Non-Goals:**
- 同步回复（#4a 已做）；#5 link；per-tenant IdP。

## Decisions

- **D1 · `im_outbound_queue` 表（agent_state.db，embedded-Y 迁移）**：列 `id, platform, address_json, payload_json, dedup_key, status(pending/sent/failed), attempts, created_at, sent_at`。**非 alembic** → 不撞管理库迁移号。
- **D2 · agent 出站 emitter mode-aware**：把 `connectors_resolver`/出站发射点抽象成一个 emitter——**managed**：写 `im_outbound_queue`（返回成功，实际发送异步）；**standalone**：现行 `connector_registry.snapshot` 进程内直发。permission_gate / cron / send_im_message 都经这同一 emitter，改 resolver 即全覆盖（permission_gate 本就用 `outbound_connectors` 抽象、不直接 import connector）。
- **D3 · node drain（`node/im_edge.py`）**：node 周期（复用 node 轮询间隔）读本机各 agent 的 `im_outbound_queue` pending 行 → 经该 agent 的 connector 发出 → 成功标 sent / 失败 attempts+1 留待重试。
- **D4 · at-least-once + dedup**：先发后标可能重发 → node 维护已发 `dedup_key`（或发送前查 sent 行）防重；dedup_key 由出站源生成（如审批请求 id + 目标）。
- **D5 · 区分 managed vs standalone**：与 #4a 同一判据（有无 node/平台注入）决定 emitter 走队列还是直发。

## Risks / Trade-offs

- **覆盖所有异步出站源**：permission_gate DM、cron fire、send_im_message——必须都经新 emitter，漏一个就在 managed 下发不出。survey 出站点（grep `outbound_connectors` / `connector_registry.snapshot` / `make_replier` 的异步用法）逐个改道。
- **at-least-once 重发**：node 崩在"发出后、标 sent 前"会重发 → dedup_key 必须可靠（审批 DM 重发比丢失好，但要 dedup 防骚扰）。测试覆盖"标记前重启→不重复发"。
- **standalone 保真**：异步出站在 standalone 必须仍进程内直发，回归测试重点（别把 standalone 也改成写队列——它没 node drain，会永远不发）。
- **drain 与连接生命周期**：node drain 依赖该 agent 的 connector 在场；agent/连接停了的待发意图——留 pending 待下次（owner-task 契约下连接随 agent 起落）。
- **顺序/时效**：队列投递比进程内直发有延迟（drain 周期）；审批 DM 可接受秒级延迟。若需更快可事件触发 drain（本切片先周期 drain，足够）。
