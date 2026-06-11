## REMOVED Requirements

### Requirement: ensure_schema 与 alembic 保持一致（漂移护栏）

**Reason**: 本要求自身定义为**过渡件**，仅在 agent 表仍混于管理库、与 alembic 双定义期间生效。持久层 #3 已把 `traces` / `memory_items` / `reflection_reports` 迁入 per-agent `agent_state.db`（嵌入式 Y），且本 change 已把它们从 alembic forward-drop——双定义期结束，护栏失去对象（KB 早已迁 Y 并被排除）。

**Migration**: schema 真相源改为单一权威——agent 侧库 = 各库统一 `MIGRATIONS`（Y，`agent_state_migrations.py` / `knowledge_base/core/migrations.py` / `memory/shared_memory_migrations.py`）；管理库 = alembic。不再需要 `ensure_schema` ↔ alembic 列一致性比对；对应 `ensure_schema()`（traces / reflection / KB operations）与护栏测试 `test_schema_drift_guard.py` 一并移除。

## ADDED Requirements

### Requirement: 管理库不再定义 traces / memory_items / reflection_reports
管理库 alembic SHALL NOT 再定义 `traces` / `memory_items` / `reflection_reports` 表——它们是 agent 侧运行时表，唯一真相源为 per-agent `agent_state.db` 的统一 `MIGRATIONS`（Y）。这三张表在 alembic 中的孤立历史定义 SHALL 经 forward-drop 迁移移除（镜像 `approvals` 的 073 处理），使管理库不再建出永不被写的孤儿 agent 表。

#### Scenario: 管理库 alembic head 不含这三表
- **WHEN** 全新管理库执行 `alembic upgrade head`
- **THEN** 库中不含 `traces` / `memory_items` / `reflection_reports` 表（已 forward-drop）

#### Scenario: agent 侧仍由 Y 建这三表
- **WHEN** 某 agent 的 `agent_state.db` 以统一 `MIGRATIONS` 打开
- **THEN** `traces` / `memory_items` / `reflection_reports` 由 Y 建立，读写经 `agent_scope` 落该 agent 的库，与管理库无关
