## Why

`per-agent-data-isolation`（PR #190）将 standalone agent 的 DB 路径从全局
`$FLEETENT_HOME/data/fleetent.db` 重定向到 `agents/<id>/data/fleetent.db`。新路径
是全新文件，从未经 alembic 迁移——`traces`、`memory_items`、`reflection_reports` 以及
所有 knowledge base 表均不存在。首次写入时报 `sqlite3.OperationalError: no such table`，
导致 traces 无法记录、memory 无法持久化、KB 功能完全失效。

## What Changes

- 在 `agent_app._start_infra()` 中新增 `_init_agent_db_schema()` 调用，在任何 store
  访问之前建立 agent DB 的完整表结构
- 各 agent-side store 暴露 `ensure_schema(db: SQLiteDatabase) -> None` 函数，内部用
  `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS`，完全幂等
- `_init_agent_db_schema()` 集中调用所有 store 的 `ensure_schema`，以 `DATABASE_URL`
  env var 指向的 DB 为目标
- alembic migrations 003-009 **不删除**，保留作为 schema 的规范来源和 platform DB
  升级路径；agent-side 建表逻辑与 migrations DDL 保持字段一致
- `scripts/install.sh` 的 `init_db()` 不变（platform DB 仍需 alembic 建
  001/002 平台表）

## Capabilities

### New Capabilities

- `agent-db-schema-self-init`: standalone agent 启动时自动建立所需 DB 表，无需外部
  alembic 步骤

### Modified Capabilities

- `agent-data-isolation`: 补充运行时 schema 初始化要求，使 per-agent DB 在 boot 后
  立即可用

## Impact

- `src/fleetent/runtime/agent_app.py` — 新增 `_init_agent_db_schema()`，在 `_start_infra()` 首行调用
- `src/fleetent/observability/traces.py` — 新增 `ensure_schema()`
- `src/fleetent/intelligence/memory/store.py` — 新增 `ensure_schema()`
- `src/fleetent/intelligence/reflection.py` — 新增 `ensure_schema()`
- `src/fleetent/intelligence/knowledge_base/operations.py` — 新增 `ensure_schema()`
- `tests/unit/` — unit tests for `_init_agent_db_schema()`
- `tests/integration/` — integration test: boot agent, verify all tables exist in per-agent DB
