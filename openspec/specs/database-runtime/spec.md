## Purpose

Define the database runtime boundary used by store modules.
## Requirements
### Requirement: Database runtime configuration

系统默认 SHALL 使用 Platform home 根目录下的 SQLite 管理库 `management.db`（持久层 tenant-first 拆分后该库只剩跨主体管理表，文件名与概念名 `management.db` 对齐）。

#### Scenario: DATABASE_URL 未设置时使用根目录 management.db
- **WHEN** 未设置 `DATABASE_URL`
- **THEN** 系统使用指向 `<FLEETENT_HOME>/management.db` 的 SQLite database_url

#### Scenario: DATABASE_URL 仍优先
- **WHEN** 设置了 `DATABASE_URL`
- **THEN** 系统使用该显式 URL
- **AND** 不强制改写为默认路径

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

### Requirement: 剩余 legacy 管理 store 迁入 db.py 边界

`user_store`（`users` / `api_keys`）与 `platform.tenancy.store`（`tenants` / `teams`）SHALL 经统一 `db.py` 边界（`create_database(Settings().database_url)` 取管理库句柄）执行 SQL，MUST NOT 再裸 `sqlite3.connect()`、MUST NOT 再以 `from user_store import DB_PATH` re-export 作为数据库入口；其 SQL SHALL 使用 named parameters。迁移引擎 `schema_migrations`（设 `PRAGMA user_version`、跑 DDL 的 schema 层本体）显式豁免本要求，可继续直接打开连接。

#### Scenario: 管理 store 经 db.py 连接
- **WHEN** `user_store` 或 `tenancy.store` 读写其表
- **THEN** 经 `db.py` 的 `SQLiteDatabase`（`execute` / `transaction`）完成，连接享 WAL + busy_timeout，不出现裸 `sqlite3.connect`

#### Scenario: 不再以 DB_PATH re-export 作 DB 入口
- **WHEN** 审视 `user_store` 与 `platform/tenancy/store.py`
- **THEN** 不存在作为数据库入口的 `DB_PATH` 裸连接路径；测试经 DB fixture / `Settings().database_url` 隔离，而非 monkeypatch `DB_PATH`

#### Scenario: 迁移引擎豁免
- **WHEN** `schema_migrations` 运行迁移
- **THEN** 允许其直接打开连接（设 `user_version`、执行 DDL），不受本要求约束

### Requirement: 外键强制启用（foreign_keys=ON）
经 `db.py` 取得的全部 SQLite 连接 MUST 在连接初始化时执行 `PRAGMA foreign_keys=ON`（与 WAL、busy_timeout 同处设置）。自此声明了外键的库（管理库 Alembic schema、KB 关系库嵌入式 DDL 的 `ON DELETE CASCADE`）其约束与级联为**真实生效语义**，不再是装饰性声明。写路径违反 FK MUST 失败（fail loud），不得静默产生孤儿引用。

#### Scenario: 连接启用 FK 强制
- **WHEN** 经 `db.py` 打开任一 SQLite 连接并查询 `PRAGMA foreign_keys`
- **THEN** 返回 1（启用）

#### Scenario: 违反 FK 的写入被拒
- **WHEN** 向管理库插入 `agents` 行且其 `tenant_id` 不存在于 `tenants`
- **THEN** 写入失败并报 FK 约束错误，不产生孤儿行

#### Scenario: KB 级联真实生效
- **WHEN** 删除一行 `knowledge_documents`
- **THEN** 其下属 `knowledge_chunks` 行随 `ON DELETE CASCADE` 一并删除，不留孤儿 chunk

### Requirement: 统一开库边界
系统 SHALL 经统一的 `db.py` 边界开库，业务层不得扩散裸 `sqlite3.connect` / `DB_PATH` re-export。开库 SHALL 经底座工厂按连接 URL scheme 选后端（`create_database` / `create_substrate` 升级为按 scheme 分派），默认 `sqlite://` 或本地路径 → 本地 SQLite 后端（行为同现状）。store 层 SQL SHALL 继续用 named parameters（`:x`），不用 `?` 风格。

#### Scenario: 经边界按 scheme 开库
- **WHEN** 任一 store 经 `db.py` 工厂以连接 URL 开库
- **THEN** 工厂按 scheme 返回对应后端
- **AND** 无 scheme / `sqlite://` 得本地 SQLite 后端

#### Scenario: 不绕过边界
- **WHEN** 检视 store 层
- **THEN** 无新增裸 `sqlite3.connect` / `DB_PATH` re-export
- **AND** 开库统一经 `db.py` 工厂

