## Purpose

Define how fleetent manages database schema lifecycle with Alembic.
## Requirements
### Requirement: Alembic migration management
The system SHALL use alembic to manage all database schema changes, with migration files checked into
the repository. Current migrations SHALL support the SQLite backend; new migration work SHALL avoid
assuming SQLite-only behavior unless explicitly documented. Each migration that creates or changes a
persistent table SHALL identify the module that owns that table, either in the migration
comment/docstring or in the corresponding OpenSpec change.

#### Scenario: Fresh install
- **WHEN** service starts on a new machine with no existing database
- **THEN** running `alembic upgrade head` creates all tables at the latest schema version

#### Scenario: Upgrade existing install
- **WHEN** a new version adds a table or column
- **THEN** running `alembic upgrade head` applies only the pending migrations without data loss

#### Scenario: Migration has module owner
- **WHEN** a migration creates or changes a persistent table
- **THEN** the migration or its OpenSpec change identifies the module that owns the table

### Requirement: Migration covers all new tables
The initial migration for this change SHALL create: `im_users`, `agents`, `user_agents`, `approvals`.

#### Scenario: Migration creates required tables
- **WHEN** `alembic upgrade head` runs on a database that only has the `users` table
- **THEN** all four new tables are created with correct columns and constraints

### Requirement: Migration URL derives from application config

`migrations/env.py` 的 online 模式 SHALL 从应用配置 `fleetent.config.Settings().database_url`
解析迁移目标 URL，覆盖 `alembic.ini` 的 `sqlalchemy.url`。仅当 `DATABASE_URL` 未设置时，SHALL
回退到 `alembic.ini` 中的默认值。app 运行时与 alembic 迁移 SHALL 永远指向同一个数据库。

#### Scenario: DATABASE_URL 指向迁移目标

- **WHEN** 设置 `DATABASE_URL=sqlite:///<tmp>/x.db` 并运行 `alembic upgrade head`
- **THEN** 所有表建立在 `<tmp>/x.db`
- **AND** 仓库内 `data/fleetent.db` 不被创建或修改

#### Scenario: 未设 DATABASE_URL 时回退默认

- **WHEN** 环境未设置 `DATABASE_URL` 并运行 `alembic upgrade head`
- **THEN** 使用 `alembic.ini` 中 `sqlalchemy.url` 的默认值

### Requirement: No raw schema creation in application code

管理面（platform / 控制面）的表 SHALL NOT 在应用启动代码中用 `CREATE TABLE IF NOT EXISTS` 创建，
SHALL 仅由 alembic 迁移建立。**agent-side 表**（`traces`、`memory_items`、`reflection_reports`、
knowledge base 表、session 元数据等）为支持单机 agent 脱离 alembic 启动，SHALL 由 store 的
`ensure_schema()` 建立；其 DDL SHALL 与 alembic head 中同名表保持一致（由漂移护栏强制，见
`agent-db-schema-self-init`）。无论哪类表，SHALL NOT 使用裸 `sqlite3.connect` 绕过统一 `db.py` runtime。

#### Scenario: 管理表只经迁移创建

- **WHEN** 应用启动
- **THEN** 不对管理表调用 `CREATE TABLE`（这些表由 alembic 拥有）

#### Scenario: agent-side 表经 ensure_schema 且与迁移一致

- **WHEN** 单机 agent 启动并调用各 store 的 `ensure_schema()`
- **THEN** 建出的 agent-side 表的列定义与 `alembic upgrade head` 的同名表一致

#### Scenario: 不绕过统一 runtime

- **WHEN** 任意 store 模块创建或访问表
- **THEN** 经由 `fleetent.db` 的 `create_database` / `SQLiteDatabase`，不出现裸 `sqlite3.connect`

#### Scenario: Existing users table
- **WHEN** alembic runs on a database with the legacy `users` table (created by `_init_db`)
- **THEN** migration treats it as already present and does not fail

### Requirement: 管理表收编完整性
`api_keys`、`audit_log`、`im_connectors` 这三张管理表 **MUST** 由 Alembic 迁移建立,其 store 模块 **MUST NOT** 再用 `_init_db` / `CREATE TABLE IF NOT EXISTS` 自建(落实既有「No raw schema creation in application code」对这三张的合规)。完成后管理库的 schema **MUST** 完全由 Alembic 拥有(连同 #2.5 已收编的 `users`)。

#### Scenario: 三张管理表由 alembic 建出
- **WHEN** 对空库执行 `alembic upgrade head`
- **THEN** schema 含 `api_keys`/`audit_log`/`im_connectors`,且这些 store 模块导入时不再调用建表 `_init_db`

#### Scenario: 已部署库迁移幂等
- **WHEN** 在已有这些表(由旧 `_init_db` 建)的库上执行迁移
- **THEN** 迁移幂等、不破坏既有数据(表已存在则 no-op)

#### Scenario: 启动不再自愈管理表
- **WHEN** 应用启动
- **THEN** 不对这三张表调用 `CREATE TABLE`;schema 须由先行的 `alembic upgrade head` 就绪
