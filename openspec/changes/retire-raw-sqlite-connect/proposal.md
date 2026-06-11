## Why

仓库里仍有 4 处业务 store 用裸 `sqlite3.connect` + `from user_store import DB_PATH`，绕过统一 `db.py` 边界（不享 WAL + busy_timeout，违反 `database-runtime` 的「迁移后 store 不得裸 connect / 暴露 DB_PATH re-export」）。其中一处还是 **agent 侧错位**：

- **`runtime/layered_budget.py`（`budget_usage` 表）**：agent 运行时分层预算计数（turns/tokens），`budget_usage` 本就是 **per-agent**（代码注释明示 cross-agent/global scope 已删、分布式按 per-agent 进程），但存储经全局 `DB_PATH` 裸 connect 落**管理库**——与 `session_anti_flap`/`sub_agent_runs` 同类的 agent-数据-落管理库 isolation 违规，`agent-runtime-db-routing-cleanup` 漏收了它；且 `budget_usage` 不在统一 `MIGRATIONS`、也不在 data-model §3.3。
- **`user_store.py`（`users`/`api_keys`）、`platform/tenancy/store.py`（`tenants`/`teams`）**：管理侧 legacy store，裸 `sqlite3.connect(DB_PATH)`，位置对（管理库）但没走 `db.py` 边界。

`schema_migrations.py` 的裸 connect 是**迁移引擎本体**（设 `user_version`、跑 DDL），合理保留，不在本切片。

## What Changes

- **`budget_usage` 归位 per-agent**：`layered_budget` 改经 `agent_scope` + `db.py`（去 `user_store.DB_PATH` + 裸 connect），DDL 折进 `runtime/agent_state_migrations.py` 统一 `MIGRATIONS`（append 在当前最大版本之后），使其在多 agent 下落各自 `agent_state.db`、不再触管理库。
- **`user_store` / `tenancy/store` 迁入 `db.py` 边界**：`_conn()` 裸 connect 改为经 `create_database(Settings().database_url)`（管理库，自动获得 WAL + busy_timeout）；SQL 统一 named parameters（`user_store` 现存 `?` 占位随迁移转 named，符合 `database-runtime` 既有要求）；移除作为 DB 入口的 `DB_PATH` re-export（确认无 importer 后）。
- **per-agent 表清单补全**：`agent-data-isolation` 的 agent 侧表集合纳入 `budget_usage`（§3.3 由 10 表更正为 11 表，归档时同步）。

不在本切片：`schema_migrations.py`（迁移引擎，裸 connect 合理）；`budget_usage` 历史行迁移（period 自然滚动重置、ephemeral，新建即可，旧管理库孤儿行由部署方按需清理）。

## Capabilities

### New Capabilities
<!-- 无；均为既有能力的需求扩展 -->

### Modified Capabilities
- `database-runtime`: `user_store` / `platform.tenancy.store` 迁入统一 `db.py` 边界——不再裸 `sqlite3.connect`、不再以 `DB_PATH` re-export 作 DB 入口、SQL 用 named parameters；`schema_migrations` 迁移引擎显式豁免。
- `agent-db-schema-self-init`: 新增 `budget_usage`（`layered_budget`）经 `agent_scope` + per-agent 嵌入式 Y 建 schema（去裸 connect / 去全局 `DB_PATH`），纳入统一 `MIGRATIONS`。
- `agent-data-isolation`: boot 后 per-agent `agent_state.db` 的 agent 侧表集合补入 `budget_usage`。

## Impact

- **代码**：`runtime/layered_budget.py`（连接改 agent_scope + db.py、删裸 connect/DB_PATH import）、`runtime/agent_state_migrations.py`（append `budget_usage` DDL）、`user_store.py`（_conn → db.py、SQL 转 named、去 DB_PATH 入口）、`platform/tenancy/store.py`（_conn → db.py）。
- **owned tables**：`budget_usage` 物理归属由管理库改为 per-agent `agent_state.db`；`users`/`api_keys`/`tenants`/`teams` 仍在管理库，仅连接路径改经 `db.py`。
- **config namespace**：无；**cross-module**：`db.py`、`tenant_router.agent_scope`、`agent_state_migrations`。
- **migration/shim**：`budget_usage` append 新 MIGRATIONS 版本（`CREATE TABLE IF NOT EXISTS` 对 legacy 幂等）；`DB_PATH` re-export 在确认无 importer 后移除（测试改用 DB fixture / Settings 注入，不再 monkeypatch DB_PATH）。
- **验证基线**：改后 agent 仍能在「无 platform、管理库表不存在」下 `fleetent agent run`，`budget_usage` 落 agent 自己的 `agent_state.db`；所有经 `db.py` 的连接享 WAL + busy_timeout。
