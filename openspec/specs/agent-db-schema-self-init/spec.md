# agent-db-schema-self-init Specification

## Purpose
standalone agent 进程（`fleetent agent run <id>`）启动时自动建立 agent DB（`agents/<id>/data/fleetent.db`）
所需的全部表结构，无需外部 alembic 步骤。每个 agent-side store 暴露幂等的 `ensure_schema()`
函数，由 `agent_app._start_infra()` 统一调用。

## Requirements

### Requirement: _start_infra initializes agent DB schema before any store access

`agent_app._start_infra()` SHALL call `_init_agent_db_schema()` as its first operation,
before session maintenance or any other infra initialization. `_init_agent_db_schema()`
SHALL create all agent-side tables in the DB pointed to by `DATABASE_URL`.

#### Scenario: Fresh agent DB gets all tables on first boot

- **WHEN** `fleetent agent run my-bot` starts with a fresh `agents/my-bot/data/fleetent.db`
- **THEN** after `_start_infra()` completes, the following tables SHALL exist:
  `traces`, `memory_items`, `reflection_reports`, `knowledge_bases`, `knowledge_documents`,
  `knowledge_chunks`, `chunks_fts`, `knowledge_source_states`

#### Scenario: Existing agent DB is unaffected (idempotent)

- **WHEN** `_init_agent_db_schema()` is called on a DB that already has all tables
- **THEN** no error is raised and no data is modified

### Requirement: Each agent-side store exposes ensure_schema

`traces.py`, `memory/store.py`, `reflection.py`, and `knowledge_base/operations.py` SHALL
each expose a public `ensure_schema(db: SQLiteDatabase) -> None` function that creates the
store's tables and indices using `CREATE TABLE IF NOT EXISTS` and
`CREATE INDEX IF NOT EXISTS`.

#### Scenario: ensure_schema creates tables idempotently

- **WHEN** `ensure_schema(db)` is called on an empty DB
- **THEN** the store's tables and indices are created

#### Scenario: ensure_schema is safe to call repeatedly

- **WHEN** `ensure_schema(db)` is called twice on the same DB
- **THEN** the second call does not raise an error

### Requirement: ensure_schema 与 alembic 保持一致（漂移护栏）

每个 agent-side store 的 `ensure_schema()` 所建表的列定义 SHALL 与 `alembic upgrade head` 产出的
同名表一致。系统 SHALL 提供一个自动护栏测试持续校验这一致性，使两套 schema 权威（alembic 升级路径 /
agent 自建路径）不会悄悄分叉。

#### Scenario: 双路建表列一致

- **WHEN** 空库 A 执行 `alembic upgrade head`，空库 B 执行全部 `ensure_schema()`
- **THEN** 对 B 中每张表，其列集合等于 A 中同名表的列集合

#### Scenario: 漂移被护栏捕获

- **WHEN** 某 `ensure_schema()` 的列定义与对应 alembic 迁移不一致
- **THEN** 护栏测试失败，并指出分叉的表与列

### Requirement: session 元数据纳入 agent DB 自建

`_init_agent_db_schema()` SHALL 调用 `session.index.ensure_schema`，使 session 元数据表随其它
agent-side 表在 boot 时一并建立于 per-agent 库。

#### Scenario: session 元数据表随 boot 建立

- **WHEN** `fleetent agent run` 完成 `_start_infra()`
- **THEN** per-agent 库中存在 session 元数据表（`sessions`），且与其它 agent-side 表同库
