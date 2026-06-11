## Purpose

Define the database runtime boundary used by store modules.
## Requirements
### Requirement: Database runtime configuration
系统 SHALL 通过统一配置项 `database_url` 决定数据库 runtime 后端。当前版本 SHALL 默认使用
SQLite 管理库 `data/management.db`（持久层 #3 拆分后该库只剩跨主体管理表，文件名与概念名 `management.db` 对齐）。

#### Scenario: 默认 SQLite database_url
- **WHEN** 未显式配置 `database_url`
- **THEN** 系统使用指向 `data/management.db` 的 SQLite database_url

#### Scenario: 旧默认路径不隐式兼容
- **WHEN** 未显式配置 `database_url`
- **THEN** 系统不会自动读取、迁移、复制或 fallback 到旧默认路径 `data/users.db`

#### Scenario: 存量 users.db 需要 operator 手动处理
- **WHEN** operator 已有本地 `data/users.db`
- **THEN** 文档说明需要手动重命名为 `data/management.db` 或重新初始化
- **AND** runtime 不执行自动迁移

#### Scenario: 不支持的 database_url
- **WHEN** `database_url` 使用当前未实现的后端 scheme
- **THEN** database runtime 初始化失败，并明确说明该后端尚未支持

### Requirement: 管理库文件名迁移（fleetent.db → management.db）
持久层 #3 之前的管理库默认文件名为 `data/fleetent.db`。系统 SHALL 提供 upgrade-time 兼容迁移：当默认数据目录下存在旧文件 `fleetent.db` 而不存在 `management.db` 时，upgrade 流程 SHALL 将主文件连同其 `-wal` / `-shm` sidecar 重命名为 `management.db`，使存量部署平滑迁移而不丢数据、不破坏 WAL 状态。该迁移 SHALL 幂等：`management.db` 已存在时不再重命名。显式配置了 `database_url` / `DATABASE_URL` 指向自定义文件名的部署 SHALL NOT 被强制重命名。

#### Scenario: 旧 fleetent.db 自动迁移为 management.db
- **WHEN** 默认数据目录存在 `fleetent.db`（及其 WAL sidecar）而无 `management.db`，operator 运行 upgrade
- **THEN** `fleetent.db` / `fleetent.db-wal` / `fleetent.db-shm` 被重命名为 `management.db` / `management.db-wal` / `management.db-shm`
- **AND** 重命名在 backup 之后、Alembic migration 之前完成

#### Scenario: 已是 management.db 时迁移幂等
- **WHEN** 默认数据目录已存在 `management.db`，operator 运行 upgrade
- **THEN** 不执行任何重命名，已有数据原样保留

#### Scenario: 自定义 database_url 不被改名
- **WHEN** operator 显式设置 `DATABASE_URL` 指向非默认文件名的本地 SQLite
- **THEN** upgrade 不重命名该文件，按其配置路径操作

### Requirement: Database adapter boundary
系统 SHALL 提供统一 database adapter 边界，供 store 模块执行 SQL、管理事务并读取结果。
新增或迁移后的 store SHALL NOT 直接调用 `sqlite3.connect()` 或暴露 `DB_PATH` re-export 作为数据库入口。

#### Scenario: Store 通过 runtime 执行 SQL
- **WHEN** 一个已迁移 store 需要查询或写入数据库
- **THEN** 它通过 database runtime 的 execute 或 transaction 接口完成操作

#### Scenario: Store 不暴露 SQLite 连接细节
- **WHEN** 调用方使用已迁移 store 的公开函数
- **THEN** 调用方不需要知道 SQLite 文件路径、连接对象或 cursor 类型

### Requirement: Named SQL parameters
新增或迁移后的 store SQL SHALL 使用 named parameters，并以 mapping 形式传递参数。新增或迁移后的
store SHALL NOT 使用 SQLite `?` 占位符风格。

#### Scenario: Named parameter query
- **WHEN** 已迁移 store 按 id 查询一条记录
- **THEN** SQL 使用 `:id` 形式的参数名，并传入包含 `id` 的参数 mapping

### Requirement: Transaction handling
database runtime SHALL 提供事务边界。事务成功退出时 SHALL 提交；事务内发生异常时 SHALL 回滚。

#### Scenario: Transaction commits
- **WHEN** 事务块内写入一条记录且没有异常
- **THEN** 事务退出后该记录可被读取

#### Scenario: Transaction rolls back
- **WHEN** 事务块内写入一条记录后抛出异常
- **THEN** 事务退出后该记录不存在

### Requirement: Result shape
database runtime SHALL 为 store 提供稳定的结果读取接口，支持读取单行、多行、影响行数，并允许 store
将行转换为 dict 或 dataclass。

#### Scenario: Fetch rows from runtime result
- **WHEN** store 执行 SELECT 查询
- **THEN** store 可以通过 runtime result 读取一行或多行结果

#### Scenario: Read affected row count
- **WHEN** store 执行 UPDATE 或 DELETE
- **THEN** store 可以读取受影响的行数

### Requirement: Reference store migration
本 change SHALL 迁移至少一个低风险 store 到 database runtime，作为后续迁移的参考实现。

#### Scenario: schedule_store uses database runtime
- **WHEN** `schedule_store.create`、`schedule_store.list_tasks`、或 `schedule_store.delete` 被调用
- **THEN** 这些函数保持原有外部行为，并通过 database runtime 访问数据库

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
