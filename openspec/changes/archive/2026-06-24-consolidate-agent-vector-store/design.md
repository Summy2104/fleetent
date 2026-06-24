## Context

`tenant_router.resolve_agent` 现给每个 agent 构造两个 `SQLiteVectorBackend`：
- `vector_backend` → `agent_vectors.db`（user memory，`mem:{user_id}`，经 `store.set_vector_backend` 注入）
- `agent_memory_vector_backend` → `agent_memory_vectors.db`（agent memory，`agentmem:`，经 `set_agent_memory_db(db, backend)` 注入）

`SQLiteVectorBackend` 的 `vector_items` 表有 `namespace` 列，所有操作 `WHERE namespace=:namespace`——同一文件天然容多 namespace。`mem:` 与 `agentmem:` 前缀不撞。所以分两个文件无技术必要，是 `resolve_agent` 历史实现碰巧分的（同 `wire-agent-memory` 前 `agent_memory.db` 关系库独立）。

`VectorFamily`/`family_of()` 是 `vector-store` spec 要求的 **namespace 家族判别逻辑入口**（防 ad-hoc `startswith`），与物理库怎么分**正交**——不在本 change 触碰。

## Goals / Non-Goals

**Goals:**
- per-agent 两向量库合并为单一 `agent_vectors.db`，按 namespace 隔离 user/agent memory 向量。
- `AgentScope` 去掉 `agent_memory_vector_backend` 字段。

**Non-Goals:**
- 删 `VectorFamily`/`family_of`（spec 锚定，保留）。
- 合并 KB 向量（per-tenant，不同 scope）。
- 数据搬迁（agent memory 向量当前空）。

## Decisions

### D1 — `resolve_agent` 构造单一 vector backend，注入两处

`resolve_agent` 只 `SQLiteVectorBackend(agent_vectors.db)` 一次，放进 `AgentScope.vector_backend`。`agent_app._init_agent_db_schema` 把这同一个实例注入：
- `memory.store.set_vector_backend(vb)`（user memory，`mem:` namespace）
- `agent_memory.set_agent_memory_db(state_db, vb)`（agent memory，`agentmem:` namespace）

消费侧零改：两者各用各的 namespace，互不可见（`search` 按 namespace 过滤）。

### D2 — 删 `AgentScope.agent_memory_vector_backend`

`AgentScope` 从 `{state_db, vector_backend, agent_memory_vector_backend}` 收为 `{state_db, vector_backend}`。`resolve_agent` 不再构造 `agent_memory_vectors.db`。

### D3 — 重建不搬数据

agent memory 向量当前空（`wire-agent-memory` 刚接通、无写入数据）。`agent_memory_vectors.db` 直接退役，旧文件残留无害（不再创建/读取）。dev/test 环境重建。

## Risks / Trade-offs

- **[同库多 namespace 串读]** → `SQLiteVectorBackend` 所有操作均 `WHERE namespace=`，`mem:`/`agentmem:` 严格隔离；加测试断言 user memory 搜不到 agent memory 向量、反之亦然。
- **[注入实例共享副作用]** → 同一 backend 实例被两个模块持有，但它无跨 namespace 状态（每次操作带 namespace 参数），共享安全。
- **[存量 dev home 残留 agent_memory_vectors.db]** → 无害（不再被 open）；可手动删，无逻辑依赖。

## Migration Plan

1. `resolve_agent` 改单 backend；删 `AgentScope.agent_memory_vector_backend`。
2. `agent_app._init_agent_db_schema` 注入同一 backend 给 store + agent_memory。
3. 重建 dev/test 验证；旧 `agent_memory_vectors.db` 忽略。
4. 回滚：恢复双 backend 构造 + 字段即可。

## Open Questions

- 无。
