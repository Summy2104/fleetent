## Why

`agent_scope` 给每个 agent 解析**两个独立向量库**：`agent_vectors.db`（user memory，`mem:{user_id}` namespace）+ `agent_memory_vectors.db`（agent memory，`agentmem:` namespace）。分文件无设计依据：

- **`SQLiteVectorBackend` 本就按 namespace 隔离**：`vector_items` 表有 `namespace` 列，`upsert`/`search`/`delete`/`clear` 全部 `WHERE namespace = :namespace`——同一文件容多 namespace 是它的设计。
- **两 namespace 不撞**：`mem:{user_id}` 与 `agentmem:` 前缀不同，同库零冲突。
- 这俩分文件只是 `resolve_agent` 历史实现碰巧分的（同合并前 `agent_memory.db` 关系库独立）。`wire-agent-memory` 已把 agent memory **关系**表收编进 `agent_state.db`，但当时（误判 "family router 决定物理库"）把**向量**层留了——这是那一片的遗留收尾。

> 澄清：`VectorFamily` / `family_of()` 是 **namespace 家族判别的逻辑入口**（`vector-store` spec 要求的规范分类器，防 ad-hoc `startswith`），与"物理向量库怎么分文件"**正交**。合并物理库不触碰 family 概念——合并后 `mem:`/`agentmem:` 仍是不同 family，只是物理同表、namespace 列区分。本 change **保留** family 概念与 spec，不删 `family_of`。

## What Changes

- **per-agent 两向量库合并为一个**：`resolve_agent` 构造**单个** `SQLiteVectorBackend`（指向 `agent_vectors.db`），同时注入给 user memory（`store.set_vector_backend`）与 agent memory（`set_agent_memory_db` 的 backend 参数）。`agent_memory_vectors.db` 退役。
- **删 `AgentScope.agent_memory_vector_backend` 字段**；`agent_scope` 只返回单一 `vector_backend`（容所有 per-agent namespace）。
- **`agent_app._init_agent_db_schema` 接线**：注入同一个 vector backend 给两处消费者。
- **消费侧零改**：user memory 仍用 `mem:{user_id}`、agent memory 仍用 `agentmem:` namespace，各取各的，互不可见。
- 趁 agent memory 向量**空**（`wire-agent-memory` 刚接通、无数据），**重建窗口、不搬数据**。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `tenant-scoped-db-routing`: `agent_scope` 的 `AgentScope` 由 `{state_db, vector_backend, agent_memory_vector_backend}` 收为 `{state_db, vector_backend}`（单一 per-agent 向量后端，容 `mem:`/`agentmem:` 多 namespace）；退役 `agent_memory_vectors.db`。
- `agent-db-schema-self-init`: per-agent 向量不再分 `agent_vectors.db` + `agent_memory_vectors.db`，统一在 `agent_vectors.db`（无独立 `agent_memory_vectors.db`）。

## Impact

- **owning packages**: `tenant_router`（`resolve_agent` 构造单 backend + `AgentScope` 删字段）。
- **public API surface**: `AgentScope` 去掉 `agent_memory_vector_backend`；`agent_memory.set_agent_memory_db(db, vector_backend)` 的 `vector_backend` 改为与 user memory 同一实例。
- **owned tables**: `vector_items`（`agent_vectors.db` 内，`mem:`/`agentmem:` 多 namespace 共存）。
- **config namespace**: 无。
- **cross-module dependencies**: `memory/store`（user mem 向量注入不变）、`memory/agent_memory`（agent mem 向量注入改用同 backend）；`memory ↛ reflection`、agent 运行时 `↛ platform` 护栏须仍绿。
- **migration / shim plan**: 重建窗口，**不搬数据**（agent memory 向量当前空）。`agent_memory_vectors.db` 直接退役，不留 shim；旧文件残留无害（不再创建/读取）。
- **OUT OF SCOPE**: 删 `VectorFamily`/`family_of`（spec 锚定的 namespace 判别入口，保留）；KB 向量 `kb_vectors.db`（per-tenant，不同 scope，不在合并内）。
- 受影响代码：`tenant_router.py`、`runtime/agent_app.py`、`memory/agent_memory.py`（向量注入）。
- **定位**：`wire-agent-memory` 的向量层收尾——关系层 `agent_memory_items` 已并入 `agent_state.db`，本片把向量层对称收编。
