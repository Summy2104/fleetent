## Why

`sqlite-wal-concurrency` 给 `db.py` 的连接加了 WAL + busy_timeout，但**向量库不经 db.py**——`vector_store/backend.py` 的 `SQLiteVectorBackend` 用自己的 `aiosqlite.connect`（upsert/search/delete 各开一次），**没有 WAL / busy_timeout**。于是向量库（KB / per-agent 记忆 / 共享记忆向量）在并发读写下仍会 `database is locked`：
- **KB 向量**：ingest 批量写（上千 chunk）时 agent 检索读 → 读被锁（最痛，用户可感）。
- **共享记忆向量**：多 agent 写撞锁（与 `shared_memory.db` 同理由，向量这半之前漏了）。

本 change 把 WAL + busy_timeout 补到向量后端的 aiosqlite 连接，是 `sqlite-wal-concurrency` 的向量孪生件，独立、低风险，建议同样早 apply。

## What Changes

- `vector_store/backend.py` 的 `SQLiteVectorBackend` 在每次 `aiosqlite.connect` 后经统一入口设 `PRAGMA journal_mode=WAL` + `PRAGMA busy_timeout=<ms>`（与 db.py 同值，复用同一常量/helper 为宜），覆盖 upsert / search / delete 等所有打开连接的路径。

不在本切片：db.py 侧（已由 `sqlite-wal-concurrency` 覆盖）；非 SQLite 向量后端（Qdrant 等自有并发）。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `vector-store`: 新增「SQLite 向量后端并发模式」要求——`SQLiteVectorBackend` 的 aiosqlite 连接 SHALL 启用 WAL + 设 busy_timeout，使向量库并发读写（ingest 写 + 检索读、共享向量多 agent 写、platform 只读投影）不撞锁失败。

## Impact

- **代码**：仅 `vector_store/backend.py`（连接入口加 PRAGMA）。
- **运行时**：每个向量库文件出现 `-wal`/`-shm` sidecar（正常）。
- **约束**：与 `sqlite-wal-concurrency` 对齐（同 busy_timeout 值、统一入口）；不碰业务。
- **依赖关系**：3c（共享向量多写）、3a-KB 向量（读写并发）受益；建议早 apply（与 `sqlite-wal-concurrency` 同期或紧随）。
- **文档**：target-arch §7（并发前提）、data-model §5.6（向量后端）。
