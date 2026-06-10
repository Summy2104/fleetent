## Why

持久层 #3 的 **3c**：把共享记忆（`shared_memory_items`，team/tenant scope）迁入 **per-tenant `shared_memory.db`**（经 `tenant_scope` + 嵌入式 Y），与 KB 平级成为 tenant 层的独立库。它是**多 agent 写的真相源**（R2-叉1），多写者协调靠 `sqlite-wal-concurrency` 的 WAL + busy_timeout，无需外置队列。

> 依赖 3a 的 `tenant_scope`（已有，KB 用）+ `sqlite-wal-concurrency`（WAL）。逻辑上不强依赖 3b-1/2/3/4（per-agent 链），但与它们都改 `tenant_router.py` → 串行协调。

## What Changes

- **`tenant_scope(tenant)` 扩展**：除 KB 句柄外，再返回**共享记忆句柄**（`shared_memory.db` 关系连接 + `shared:` 向量后端）。`<tenant>/shared_memory.db` + `shared_memory_vectors.db`。
- `memory/shared.py`（`shared_memory_items`）DDL lift 进 per-tenant 共享库 `MIGRATIONS`；连接走 `tenant_scope`；**agent 拿读写句柄**（区别于 KB 的只读）。
- 多 agent 写靠 **WAL + busy_timeout**（`sqlite-wal-concurrency`）原生串行化；写为低频经审批门/手工，无需应用层锁/队列。

不在本切片：platform 只读投影**实现**（依赖 3d 只读 router；本切片只把共享记忆落 per-tenant 库）；fan-out（3d）。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `tenant-scoped-db-routing`: `tenant_scope(tenant)` 新增返回**共享记忆**句柄（`shared_memory.db` 关系 + `shared:` 向量），与 KB 同主体作用域；SQLite 后端映射 `<tenant>/shared_memory.db` + `shared_memory_vectors.db`。
- `memory-layer`: shared memory 的 schema 经 per-tenant `shared_memory.db`（`tenant_scope` + 嵌入式 Y）建立；agent 经 tenant_scope 取**读写**连接；多写者协调由连接层 WAL + busy_timeout 提供，不引入应用层锁/队列。

## Impact

- **代码**：`tenant_router`（tenant_scope 加共享记忆句柄 + 后端路径）；`memory/shared.py`（连接走 tenant_scope、DDL lift）；`vector_store` `shared:` 路由到共享记忆向量库。
- **数据/schema**：shared_memory_items 移到 per-tenant `shared_memory.db`；上线前不迁移数据。
- **约束**：per-tenant 库走 Y；多写者靠 WAL（关系库 `sqlite-wal-concurrency` + **向量库 `vector-backend-wal-concurrency`**）；不 import platform。
- **依赖**：3a（tenant_scope）+ `sqlite-wal-concurrency`（关系库 WAL）+ `vector-backend-wal-concurrency`（共享向量库多写需向量后端 WAL）。**与 3b-1/3d 同改 tenant_router → 串行协调。**
- **文档**：data-model.md §5.1/§5.7、roadmap R2-叉1。
