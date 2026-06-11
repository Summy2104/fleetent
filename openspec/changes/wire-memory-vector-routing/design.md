## Context

memory 关系侧已 per-agent(`memory_items` → `agent_state.db`，`set_state_db`，去 namespace 列),但向量侧仍用全局 `vector_store` + `mem:{user_id}` namespace(`search.py:15`、`operations.py`、`extraction.py`、`maintenance.py`)。`agent_scope` 提供 `AgentScope.vector_backend`(`agent_vectors.db`)但全仓没人用——与 X 之前 KB 向量同源的"没接通"。

shared memory 是现成参照:`set_shared_memory_db(db, vector_backend)` 注入 per-tenant 向量后端,`_shared_memory_backend().search(query_vector, namespace, limit)` / `.upsert` / `.delete`——用注入后端 + 保留 namespace,embedding 仍走全局 `vector_store.embed_text`。

## Goals / Non-Goals

**Goals:**
- memory 向量经注入的 per-agent `agent_vectors.db` 后端(`agent_scope.vector_backend`),去全局 `vector_store` backend 旁路。
- `mem:{user_id}` namespace 保留为 per-agent 向量库内按用户分区(与 shared 一致)。
- 多 agent 向量物理隔离。

**Non-Goals:**
- KB 向量(X 处理)。
- memory 数据迁移(无存量真实数据)。
- 改 embedding provider(仍全局 `vector_store.embed_text`)。
- 改 memory 关系侧(已 per-agent)。

## Decisions

### D1：照 shared memory 模式注入 per-agent 向量后端
memory 加注入口(随 `set_state_db` 一并传 vector_backend,或单独 `set_vector_backend`);`agent_app` boot 注入 `agent_scope(tenant, agent_id).vector_backend`。内部 `_memory_backend()` 取注入后端(未注入则按基线报错/降级,与 store 一致)。**为何随 set_state_db**:memory 关系与向量同属 per-agent、同一 boot 注入点,合并 setter 减少接线点;但若现有 `set_state_db` 签名被广泛调用,可加独立 `set_vector_backend` 避免破坏调用方——apply 时按实际调用面决定。

### D2：upsert/search/delete 改注入后端,embedding 仍全局,namespace 保留
- search:`vector_store.embed_text(query)` 得 query_vector → `_memory_backend().search(query_vector, mem_ns, limit)`(对照 shared.py:142)。
- operations/extraction/maintenance:`vector_store.upsert/delete(id, content, mem_ns)` → 先 embed(写入时)再 `_memory_backend().upsert(id, vector, mem_ns)` / `.delete(id, mem_ns)`。
- `mem:{user_id}` namespace 保留(per-agent 向量库内多用户分区)。
**为何保留 namespace**:一个 agent 的 `agent_vectors.db` 承载该 agent 下多个 user 的记忆向量,namespace 做用户分区——与 shared memory(per-tenant 文件 + `shared:` namespace)同构。

### D3：spec delta 放 memory-layer，不碰 tenant-scoped-db-routing
X 已 MODIFY `tenant-scoped-db-routing` 的「agent 侧 store 连接来自路由」(为 KB)。本 change 若也改它会撞同一 requirement。memory 向量行为由 `memory-layer` 的「Vector index synchronization / Semantic memory search」描述,改这两条即可,**与 X 不冲突**。

## Risks / Trade-offs

- [setter 签名变更破坏现有 `set_state_db` 调用方] → 优先加独立 `set_vector_backend`(不动 set_state_db 签名);或 boot 一处调用、影响面小。apply 时 grep 调用面定夺。
- [向量从全局切到 per-agent backend，召回行为变化] → 应等价(同 user namespace 范围);加 ingest→search 检索回归对照。
- [memory 模块多处(4 文件)用全局 vector_store 漏改] → grep `vector_store.search|upsert|delete` 全 memory 模块 + 护栏测试断言无全局旁路(embed_text 除外)。
- [agent_vectors.db 此前未真正打开/建立] → 确认 `agent_scope.vector_backend` 实例化即建库(对照 shared/KB 的 open 行为)。

## Migration Plan

1. memory 加向量后端注入口 + `_memory_backend()`。
2. search/operations/extraction/maintenance 去全局 `vector_store` backend、改注入后端(embed 仍全局,namespace 保留)。
3. `agent_app` boot 注入 `agent_scope.vector_backend`。
4. 护栏测试 + 检索回归;同步 data-model §3.6 / memory.md(memory 向量 = per-agent agent_vectors.db)。
5. 回滚:纯向量路由变更,无数据迁移;回滚还原注入与调用。

## Open Questions

- setter 合并(set_state_db 带 vector_backend)还是独立(set_vector_backend)——按现有 set_state_db 调用面定(倾向独立,少破坏)。
