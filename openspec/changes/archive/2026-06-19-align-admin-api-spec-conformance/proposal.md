## Why

`add-platform-admin-apis`（已落地 main，commit a8cb2885）归档时，几条 spec 被软化以迁就实现：创建/删除端点的状态码由 201/204 退成笼统的"成功响应"（实现返回 200），注销冲突的 409 丢了"列出被 pin agent"的可运维要求。本 change 把这些 REST 语义与可运维性**重新收紧到 spec 并修正实现**，让两者在更正确的行为上一致。

> 核实：approver 路由（`PATCH /admin/tenancy/approvers/{entity_id}`）与共享记忆 actor（以认证 admin 身份为准、不收 body `actor`）在合并后的权威 spec 中**已与实现对齐**，本 change 不涉及。

## What Changes

- **状态码收紧（改 spec + 改代码）**：
  - `POST /admin/memory/shared` 创建成功 → **201**（现 200）
  - `DELETE /admin/nodes/{id}` 注销成功 → **204**（现 200）
  - `DELETE /admin/nodes/{id}/pin` unpin 成功 → **204**（现 200）
- **409 补 pin 列表（改 spec + 改代码）**：注销仍有 agent pin 的 node 时，409 响应体 MUST 列出被 pin 的 agent（便于运维知道先解除谁），实现用 `placement_store.list_by_node` 填充。
- 同步更新被固化为 200 / 裸 409 的测试断言。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities

- `agent-node-registry`：注销/unpin 状态码收紧为 204；注销冲突 409 体含被 pin agent 列表。
- `shared-memory-admin-api`：创建返回 201。

## Impact

**owning package**：`platform`（`node_management/node_admin_api.py`、`shared_memory_management/shared_memory_admin_api.py`）

**public API surface**：状态码语义修正（201/204）；409 体新增 pin 列表字段

**owned tables**：无　**config namespace**：无　**migration**：无

**cross-module dependencies**：node deregister 409 路径调用 `placement_store.list_by_node` 取被 pin agent 列表填充响应（platform 内部，无新跨模块契约）
