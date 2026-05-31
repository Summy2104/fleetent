## ADDED Requirements

### Requirement: Database runtime configuration
系统 SHALL 通过统一配置项 `database_url` 决定数据库 runtime 后端。当前版本 SHALL 默认使用
SQLite 数据库 `data/users.db`。

#### Scenario: 默认 SQLite database_url
- **WHEN** 未显式配置 `database_url`
- **THEN** 系统使用指向 `data/users.db` 的 SQLite database_url

#### Scenario: 不支持的 database_url
- **WHEN** `database_url` 使用当前未实现的后端 scheme
- **THEN** database runtime 初始化失败，并明确说明该后端尚未支持

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
