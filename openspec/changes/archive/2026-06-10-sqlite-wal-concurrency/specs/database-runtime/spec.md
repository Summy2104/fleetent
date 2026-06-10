## ADDED Requirements

### Requirement: SQLite 并发模式（WAL + busy_timeout）

经 `db.py` 建立的 SQLite 连接 SHALL 启用 WAL 日志模式（`PRAGMA journal_mode=WAL`）并设置一个非零的 `busy_timeout`。所有打开 SQLite 连接的路径（`execute` 及游标/迭代等）MUST 经同一内部连接入口统一应用该配置，使**所有经 `db.py` 的 SQLite 库**（管理库 / KB / per-agent / 共享记忆）一致受益。目的：并发读写——尤其 **platform 只读投影读 + agent 写**（target-arch §7）、共享记忆**多 agent 写**——不因默认 rollback journal 或零超时而立即 `database is locked` 失败。

#### Scenario: 连接启用 WAL

- **WHEN** 经 `db.py` 打开一个 SQLite 库连接
- **THEN** 该库的 `journal_mode` 为 `wal`

#### Scenario: 连接设置 busy_timeout

- **WHEN** 经 `db.py` 打开一个 SQLite 库连接
- **THEN** 该连接的 `busy_timeout` 为配置的非零值（撞锁时等待重试而非立即失败）

#### Scenario: 读不阻塞写、写不阻塞读

- **WHEN** 一个连接正在写某库，另一个连接同时读同库（如 platform 只读投影）
- **THEN** 读取在 WAL 下正常返回，不因写入而报 `database is locked`

#### Scenario: 并发写撞锁短暂等待

- **WHEN** 两个连接近乎同时写同一库
- **THEN** 后者在 `busy_timeout` 内等待先者提交后成功，而非立即失败
