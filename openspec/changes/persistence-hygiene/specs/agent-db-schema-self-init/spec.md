# agent-db-schema-self-init Delta Spec

## ADDED Requirements

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
