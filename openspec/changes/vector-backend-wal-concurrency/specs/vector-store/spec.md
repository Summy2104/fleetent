## ADDED Requirements

### Requirement: SQLite 向量后端并发模式（WAL + busy_timeout）

`SQLiteVectorBackend` 的 aiosqlite 连接 SHALL 启用 WAL 日志模式（`PRAGMA journal_mode=WAL`）并设非零 `busy_timeout`，经同一连接入口统一应用，覆盖 `upsert` / `search` / `delete` 等所有打开连接的路径。目的：向量库并发读写——KB ingest 写 + 检索读、共享记忆向量多 agent 写、platform 只读投影——不因默认 journal/零超时而 `database is locked`。busy_timeout SHOULD 与 `db.py`（`database-runtime` SQLite 并发模式）取同值。

#### Scenario: 向量后端连接启用 WAL

- **WHEN** `SQLiteVectorBackend` 打开 aiosqlite 连接
- **THEN** 该向量库 `journal_mode` 为 `wal`、连接 `busy_timeout` 为非零值

#### Scenario: 向量库读不阻塞写

- **WHEN** 一连接正写向量库（如 KB ingest upsert），另一连接同时检索读
- **THEN** 读取在 WAL 下正常返回，不报 `database is locked`

#### Scenario: 向量库并发写短暂等待

- **WHEN** 两连接近乎同时写同一向量库（如多 agent 写共享向量）
- **THEN** 后者在 busy_timeout 内等待先者提交后成功，而非立即失败
