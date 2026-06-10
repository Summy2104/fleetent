## Why

持久层 #3 的 **3b-2**：继 3b-1（router 泛化 + session 元数据迁 per-agent 库）之后，把 `traces` 与 `reflection` 两个 agent 侧 store 也迁入 per-agent `agent_state.db`（经 `agent_scope` + 嵌入式 Y），从 `ensure_schema`-into-global 退役。机械重复 3b-1 的套路，无新设计。

> 假设 3b-1 的 `agent_scope(tenant, agent)` / `agent_state.db` / per-agent `MIGRATIONS` 契约（已 propose 于 `agent-scoped-db-routing`）；apply 前复核 3b-1 落地形状，有出入则微调 tasks。

## What Changes

- `observability/traces.py`（`traces` 表）与 `reflection/reflection.py`（`reflection_reports` 表）的 DDL **lift 进 per-agent 库 `MIGRATIONS`**（追加版本步）。
- 二者连接从 `create_database`/`ensure_schema`-into-global 改为经 **`agent_scope(tenant, agent_id).state_db`** + migrate-on-open。
- `agent_app._init_agent_db_schema` 中 traces/reflection 部分接线到 agent_scope。
- 单主体 `default` 先（多主体 fan-out 留 3d）。

不在本切片：memory（3b-3，含去 namespace）、approvals（3b-4）；共享记忆（3c）；fan-out + 投影（3d）。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `agent-db-schema-self-init`: 新增「traces / reflection 经 per-agent 嵌入式 Y + `agent_scope` 建 schema」要求——二者不再 `ensure_schema`-into-global，schema 随 per-agent 库 `MIGRATIONS` 迁移。

## Impact

- **代码**：`observability/traces.py`、`reflection/reflection.py`（连接走 agent_scope、DDL lift 进 per-agent MIGRATIONS）；`agent_app._init_agent_db_schema`（接线）。
- **数据/schema**：traces/reflection_reports 移到 `agent_state.db`（DDL 不变）；上线前不迁移数据。
- **约束遵守**：per-agent 库走嵌入式 Y、非 alembic；不得 import platform；统一经 db.py/router 边界。
- **依赖**：3b-1（`agent_scope`/per-agent 库）。**与 #4 / 3b-1 同改 `agent_app` → apply 串行排在 3b-1 后。**
- **依赖文档**：data-model.md §5.1/§5.2/§5.7。
