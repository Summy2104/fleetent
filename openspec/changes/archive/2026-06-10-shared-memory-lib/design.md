## Context

3c 把共享记忆落 per-tenant `shared_memory.db`。现状：`memory/shared.py` 的 `create_shared_memory` 等 INSERT/UPDATE `shared_memory_items`，写者 = agent（经 reflection 提案/审批门）+ admin_cli（手工），低频。`db.py` 当前无 WAL（由 `sqlite-wal-concurrency` 补）。

## Goals / Non-Goals

**Goals:** 共享记忆迁 per-tenant `shared_memory.db`（tenant_scope+Y）；多 agent 写靠 WAL+busy_timeout。
**Non-Goals:** platform 只读投影实现（3d）；fan-out（3d）；改共享记忆业务语义。

## Decisions

**D1 共享记忆挂 `tenant_scope`（per-tenant），agent 拿读写句柄。** 区别于 KB（agent 只读、ingest 写）：共享记忆是多 agent 写的真相源（R2-叉1）。
**D2 多写者 = WAL + busy_timeout 原生串行，无外置队列。** 写低频经门/手工，SQLite 原生足够（见 `sqlite-wal-concurrency`）。"单一写者域"指单一写者-类（agent，不混 ingest），协调交 SQLite。
**D3 关系 + 向量两 substrate（模型 A）。** `shared_memory.db` + `shared_memory_vectors.db`，`shared:` 家族路由。

## Risks / Trade-offs

- **WAL 未先落地则多写撞锁。** → 硬依赖 `sqlite-wal-concurrency` 先 apply。
- **与 3b-1/3d 同改 tenant_router。** → 串行；tenant_scope 扩展接 3b-1 落地形状。
- **platform 投影衔接。** → 投影 impl 留 3d；本切片确保数据在 per-tenant 库、将来可只读。

## Migration Plan

1. tenant_scope 扩展返回共享记忆句柄 + 后端路径；shared_memory DDL lift 进 per-tenant MIGRATIONS。
2. memory/shared.py 连接走 tenant_scope（读写）；`shared:` 向量路由到共享记忆向量库。
3. 回归（含多写并发，依赖 WAL）+ 门禁。回滚 = revert。
