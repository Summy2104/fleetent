## MODIFIED Requirements

### Requirement: Each agent-side store exposes ensure_schema

`traces.py`, `memory/store.py`, and `reflection.py` SHALL each expose a public
`ensure_schema(db: SQLiteDatabase) -> None` function that creates the store's tables and
indices using `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`（过渡态，后续切片迁入
嵌入式迁移 Y）。`knowledge_base/operations.py` SHALL NOT 再以 `ensure_schema` 自建——KB 关系库 schema
改由 `embedded-schema-migration`（Y）管理（KB 为 Y 首个消费者）。

#### Scenario: ensure_schema creates tables idempotently

- **WHEN** `ensure_schema(db)` is called on an empty DB
- **THEN** the store's tables and indices are created

#### Scenario: ensure_schema is safe to call repeatedly

- **WHEN** `ensure_schema(db)` is called twice on the same DB
- **THEN** the second call does not raise an error

#### Scenario: KB schema 不再走 ensure_schema

- **WHEN** 初始化 KB 关系库
- **THEN** 其 schema 由嵌入式迁移引擎（Y）建立，而非 `knowledge_base/operations.py:ensure_schema()`

### Requirement: ensure_schema 与 alembic 保持一致（漂移护栏）

每个**仍以 `ensure_schema()` 自建**的 agent-side store（traces/memory/reflection），其所建表的列定义 SHALL
与 `alembic upgrade head` 产出的同名表一致。系统 SHALL 提供一个自动护栏测试持续校验这一致性，使两套 schema
权威（alembic 升级路径 / agent 自建路径）不会悄悄分叉。本护栏为**过渡件**（data-model §5.2）：仅在 agent 表
仍混于 `fleetent.db`、与 alembic 双定义期间生效；已迁入 Y 的库（如 KB 关系库）不在其校验范围。

#### Scenario: 双路建表列一致

- **WHEN** 空库 A 执行 `alembic upgrade head`，空库 B 执行全部仍存的 `ensure_schema()`
- **THEN** 对 B 中每张表，其列集合等于 A 中同名表的列集合

#### Scenario: 漂移被护栏捕获

- **WHEN** 某 `ensure_schema()` 的列定义与对应 alembic 迁移不一致
- **THEN** 护栏测试失败，并指出分叉的表与列

#### Scenario: Y 管理的库不在漂移校验内

- **WHEN** KB 关系库已由嵌入式迁移（Y）管理
- **THEN** 漂移护栏不把 KB 表纳入 ensure_schema↔alembic 一致性校验
