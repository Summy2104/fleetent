## Context

`node/reconcile.py` 的 `_status_payload(agent_id, pid)` 只发 phase/pid;在 line 80 用 `self._backend.is_alive(name)` 调用。平台 `POST /nodes/{id}/status` 与 `node_store` 已含 `health` 字段(只是节点没发)。④ 给 backend 加了 `gateway_port(agent_name)`,且托管 agent 在该 loopback 端口提供 `/health`(`{"status":"ok",...}`)。

## Goals / Non-Goals

**Goals:** 节点判定并上报每个 running agent 的真实 health;探测舱壁化;`node_agent_status.health` 不再 null。
**Non-Goals:** 不改平台 status 端点/存储;不做花哨监控维度(degraded 级别先不引入,留 healthy/unhealthy 二态);不碰 agent 运行时核心。

## Decisions

**D1 · 用 loopback `/health` 探活。** 对每个有 `gateway_port` 的 running agent,`GET http://127.0.0.1:{port}/health`(短超时,复用 node 已有 httpx):200 → `healthy`,非 200 / 连不上 → `unhealthy`。无端口的 agent(理论上托管都有)回退:`is_alive` → `healthy`。

**D2 · 舱壁化。** 单 agent 探测异常/超时 → 该 agent 记 `unhealthy`,catch 不外抛,不影响其它 agent 的上报、不杀 reconcile 循环(遵循异步资源/关停舱壁化原则)。

**D3 · 平台侧零改动。** `health` 字段链路已通(端点 + store),只补节点发送端。

**D4 · 二态先行。** 先 healthy/unhealthy;`degraded` 留给后续(需要更细的探测语义时再加),避免现在过度设计。

## Risks / Trade-offs

- **[探测拖慢 reconcile]** → 短超时 + 舱壁化;探测在上报前对各 agent 做,失败快速归为 unhealthy。
- **[与并行项冲突]** → 只动 node/reconcile.py(及 backend 暴露 gateway_port),与在跑的 agent 侧 / 前端项零重叠;主会话串行合。
- **[health 语义]** → 明确 `/health` 200=healthy 的简单判定;真正"degraded"(部分降级)留后续。
