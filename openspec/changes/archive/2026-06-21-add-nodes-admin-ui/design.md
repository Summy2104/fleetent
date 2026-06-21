## Context

C1 港域范式已坐实。Nodes 是 **net-new UI**:legacy 没有 nodes tab(`node_admin_api` 是后来加的、零 UI),所以没有 parity 基线,按后端 API 能力建。后端:`/admin/nodes` 提供 list/register/delete + pin/unpin(agent↔node 放置,基于 `placement_store`)。

## Goals / Non-Goals

**Goals:** 运维在 SPA 看节点(身份/labels/last_seen)、注册/删除节点、把 agent pin/unpin 到节点;TDD + MSW。
**Non-Goals:** 不改 node 后端 API;不做节点级实时监控大盘(超出本切片);不动其它域。

## Decisions

**D1 · 照 agents 范式。** `features/nodes/api.ts`:`useNodesQuery`(列表)+ `useRegisterNode`/`useDeleteNode`/`usePinAgent`/`useUnpinAgent`,mutation 后失效 `['nodes']`(及放置列表)。`page.tsx`:节点列表 + 注册表单 + 删除确认 + 每节点的 agent 放置(pin/unpin)。

**D2 · 高危二次确认。** 删除节点会影响其上 agent 放置 → 删除需二次确认(沿用既有 X-Confirm 约定,若后端要求)。

**D3 · net-new 无 parity,以 API 能力为准。** 字段/操作以 `node_admin_api` 实际返回与端点为准,不臆造监控维度;后续要更丰富的节点状态再单独迭代。

**D4 · routes.tsx 共享缝。** 注册 nodes(import + NavLink + Route),不涉及 legacyLinks(nodes 从来不在里面)。`routes.test.tsx` 用 `within(nav)` scope。

## Risks / Trade-offs

- **[net-new 易过度设计]** → 严格按现有 API 能力建(list/register/delete/pin/unpin),不做后端没有的监控大盘。
- **[误删节点]** → 二次确认 + 清晰文案(影响 agent 放置)。
- **[与同期前端域撞 routes.tsx]** → 合并由主会话串行做。
