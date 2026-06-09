# db-migration Delta Spec

## ADDED Requirements

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

## MODIFIED Requirements

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
