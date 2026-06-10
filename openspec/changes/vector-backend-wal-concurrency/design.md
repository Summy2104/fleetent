## Context

`sqlite-wal-concurrency` 只覆盖 db.py 的连接；`vector_store/backend.py:SQLiteVectorBackend` 用 `aiosqlite.connect`（upsert:43 / search:71 / delete:96 各开一次新连接），无 WAL/busy_timeout。向量库的并发读写（KB ingest 写+检索读、共享向量多 agent 写）因此仍会撞锁。

## Goals / Non-Goals

**Goals:** 向量后端 aiosqlite 连接加 WAL + busy_timeout，与 db.py 对齐。
**Non-Goals:** db.py 侧（已覆盖）；非 SQLite 向量后端；改向量检索语义。

## Decisions

**D1 与 db.py 同模式、同值。** WAL（库级持久）+ busy_timeout（连接级），经向量后端统一连接入口设置；busy_timeout 复用 db.py 的常量/同值（如 5000ms），避免两套数。
**D2 覆盖所有打开连接的路径。** upsert/search/delete 都经统一入口，别只改一处。

## Risks / Trade-offs

- **aiosqlite 异步下设 PRAGMA：** 在 connect 后 `await db.execute("PRAGMA ...")` 即可。→ 测试覆盖。
- **每 op 开新连接 → 每次设 PRAGMA：** busy_timeout 必须每连接设；WAL 幂等（库级持久）。开销可忽略。

## Migration Plan

1. 向量后端加统一连接入口（connect + WAL + busy_timeout），upsert/search/delete 都走它。
2. 并发测试（一连接写、另一读不锁；两写 busy_timeout 内成功）+ 回归。回滚 = revert（仅连接行为）。
