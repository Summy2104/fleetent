## Why

`node_agent_status.health` 当前恒为 `null`——节点上报实际态只发 `phase`/`pid`(`node/reconcile.py` 的 `_status_payload` 不带 health),平台侧其实**已接受并存储** `health`(`POST /nodes/{id}/status` + `node_store`)。所以这是个纯节点侧缺口:节点没去判定并上报每个 agent 的健康。④ 落地后节点已知每个托管 agent 的 loopback 端口(`backend.gateway_port`),agent 也在该端口提供 `/health`,正好用来探活。

## What Changes

- 节点上报实际态时,为每个 running agent **探测其 loopback `/health`** 并填 `health`:`GET http://127.0.0.1:{gateway_port}/health` 返回 200 → `healthy`,否则 → `unhealthy`;无端口的 agent 回退按进程存活(alive → `healthy`)。
- 探测**舱壁化**:单个 agent 探测失败 → 标 `unhealthy`,不影响其它 agent、不杀 reconcile 循环。
- `_status_payload` 增加 `health` 字段一并 POST。平台侧不改(已存 health)。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `node-supervisor`: 「上报实际态」新增——节点 SHALL 通过探测 agent 的 loopback `/health` 判定并上报每个 running agent 的 `health`(healthy/unhealthy),探测舱壁化。

## Impact

- **改动**:`src/fleetent/node/reconcile.py`(`_status_payload` + 探测逻辑);可能小动 `node/backend.py` 暴露 `gateway_port`(④ 已加)。
- **后端平台**:不改(`POST /nodes/{id}/status` 与 `node_store` 已接受/存储 health)。
- **边界**:纯节点侧;不碰 platform/frontend/agent 运行时核心;无 schema(health 列已存在)。**与在跑的 wire-agent-reflection-trigger(agent 侧)/ 前端域 / agent-bindings-native 全零重叠**,可立即并行;合并由主会话串行做。
- **效果**:Nodes UI(待做)与运维能看到真实 agent 健康,不再恒 null。
