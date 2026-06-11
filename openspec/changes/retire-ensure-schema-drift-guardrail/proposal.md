## Why

`agent-db-schema-self-init` 的「ensure_schema 与 alembic 一致（漂移护栏）」是 **过渡件**——其自身定义为「仅在 agent 表仍混于 `fleetent.db`、与 alembic 双定义期间生效」。持久层 #3 把 agent 侧表迁入 per-agent `agent_state.db`（嵌入式 Y）后，本应像 `approvals`（migration 073 forward-drop）一样把 `traces` / `memory_items` / `reflection_reports` 也从 alembic 移除，结束双定义、退役护栏。

但**这步没做完**：alembic head 至今仍定义 `traces` / `memory_items` / `reflection_reports`（只有 003/004/005 各自的 downgrade，无 forward-drop），与 Y 形成**双定义**。后果：管理库被 `alembic upgrade head` 建出永不被写的孤儿 agent 表；`traces.ensure_schema` / `reflection.ensure_schema` 仅因被漂移护栏测试调用而"活着"；`knowledge_base/operations.ensure_schema` 则已彻底死（KB 早迁 Y、被护栏排除）。这是和 approvals/budget 一路同源的"切了一半"。

## What Changes

- **forward-drop 三张孤儿表出 alembic**：新增 alembic 迁移 drop `traces` / `memory_items` / `reflection_reports`（镜像 073 drop approvals 的做法），使管理库不再定义 agent 侧表，结束双定义。
- **退役漂移护栏**：移除 `agent-db-schema-self-init` 的「ensure_schema 与 alembic 一致」requirement（过渡件，退役条件已满足）；删除其护栏测试 `tests/integration/test_schema_drift_guard.py`。
- **删随之变死的 ensure_schema**：`observability/traces.py`、`reflection/reflection.py`、`knowledge_base/operations.py` 的 `ensure_schema()`（退役护栏后无任何调用方）。schema 真相源 = 各库统一 `MIGRATIONS`（Y）/ alembic（管理）。
- **不动**：`schedule_store.ensure_schema`（`scheduled_tasks` 经 db.py 自建、非 alembic、非本护栏覆盖——仍 live）。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `agent-db-schema-self-init`: **移除**「ensure_schema 与 alembic 保持一致（漂移护栏）」requirement（过渡件，agent 表已迁 Y 且本 change 从 alembic forward-drop，双定义结束）；**新增**「管理库不再定义 traces/memory_items/reflection_reports」要求（孤立定义经迁移 drop，agent 侧为唯一真相源）。

## Impact

- **代码**：新增 alembic 迁移（drop 三表）；删 `observability/traces.py`、`reflection/reflection.py`、`knowledge_base/operations.py` 的 `ensure_schema()`；删 `tests/integration/test_schema_drift_guard.py`；按需调整 `tests/integration/test_traces_reflection_agent_scope.py`（其"agent_app 不调用 traces.ensure_schema"的守卫在函数移除后退化为恒真，改为校验 schema 来自统一 MIGRATIONS 或直接移除该用例）。
- **owned tables**：`traces` / `memory_items` / `reflection_reports` 的 **alembic（管理库）孤立定义**被 drop；它们的 agent 侧 Y 定义（`agent_state_migrations.py`）不变、仍是唯一真相源。
- **数据**：被 drop 的是管理库中**永不被写的空孤儿表**（#3 后所有读写经 `agent_scope` 落 agent_state.db）——无数据损失。
- **config / cross-module**：无。
- **migration/shim**：alembic forward-drop（downgrade 可重建空表）；幂等性由 alembic 版本链保证。
- **验证基线**：改后 `alembic upgrade head` 的管理库不再含 traces/memory_items/reflection_reports；agent `fleetent agent run` 仍正常（schema 来自 Y）。
