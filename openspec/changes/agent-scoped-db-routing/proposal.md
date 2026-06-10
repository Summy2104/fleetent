## Why

持久层 roadmap **#3 的 3b-1**：把 3a 立的"租户作用域路由 + 嵌入式迁移（Y）"地基**泛化到 per-agent 粒度**，并以 **session 元数据索引**作为第一个 per-agent 消费者验证。3a 的 router 只建模了 per-tenant（`scope(tenant) → KbScope`）；但 per-agent 资源（运行库/记忆向量）是 **per-(tenant, agent)** 粒度，今天 `session/index.py`、`traces`、`memory`、`reflection`、`approvals` 等仍在 `fleetent.db` 上靠 `ensure_schema` 自建。3b-1 立 per-agent 库 + `agent_scope` 解析器，后续 3b-2/3/4 逐个把其余 store 迁入。设计已定（data-model §5.7 物理布局与命名约定 + B2）。

## What Changes

- **泛化 router 为两个平级 typed 解析器**：`tenant_scope(tenant)`（= 原 `scope`，给 KB/共享记忆等 per-tenant 资源）+ **新增 `agent_scope(tenant, agent_id)`**（给 per-agent 资源）。`<tenant>/<agent_id>/` 目录包含关系沉进 `SQLiteTenantBackend` 的路径计算，调用点不变。
- **立 per-agent 库 + 命名约定**：`agent_scope` 返回 `AgentScope{state_db, vector_backend}`，SQLite 后端映射到 `<tenant>/<agent_id>/agent_state.db` + `agent_vectors.db`（命名规则见 data-model §5.7）。
- **session 元数据索引迁入 per-agent 库（第一个消费者）**：`session/index.py`（`sessions` 元数据表 + 相关运行表 `session_anti_flap`/`sub_agent_runs` 等 DB 表）从 `ensure_schema`-into-global 改为经 `agent_scope` 取 `agent_state.db` + 嵌入式 Y（migrate-on-open）。DDL 原样 lift 进 per-agent 库的 `MIGRATIONS`。
- **boot 接线**：`agent_app._init_agent_db_schema` 中 session 那部分改走 `agent_scope`；traces/memory/reflection 暂留 `ensure_schema`（3b-2/3/4 再迁）。
- **单主体 `default` 先**：`agent_scope("default", agent_id)`；多主体目录 fan-out 留 3d。

不在本切片：traces/memory/reflection/approvals 迁 Y（3b-2/3/4）；共享记忆库（3c）；多主体 fan-out + platform 只读投影（3d）；session **内容 JSON 文件**（`session/manager.py` 的 `SESSIONS_DIR`，单机已在 agent home 下，多主体路由留 3d）——本切片只迁 session 的**元数据 DB 表**。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `tenant-scoped-db-routing`: 路由从单一 `scope(tenant)` 泛化为两个平级 typed 解析器——`tenant_scope(tenant)`（per-tenant 资源）+ `agent_scope(tenant, agent_id)`（per-agent 资源，返回 `agent_state.db` + `agent_vectors.db` 句柄）；`<tenant>/<agent_id>/` 包含关系沉进后端。单主体先行不变。
- `agent-db-schema-self-init`: session 元数据索引（`session/index.py`）的 DB 表加入「迁入嵌入式 Y、经 `agent_scope` 取 per-agent `agent_state.db`」之列（继 KB 之后第二个迁出 `ensure_schema`-into-global 的 store）；traces/memory/reflection 仍 `ensure_schema`（过渡）。

## Impact

- **代码**：`tenant_router.py`（加 `agent_scope` + `AgentScope` + 后端 per-agent 路径；`scope`→`tenant_scope` 重命名，调用点同步）；`session/index.py`（连接走 agent_scope、DDL lift 进 per-agent MIGRATIONS）；`agent_app._init_agent_db_schema`（session 部分接线）。
- **数据/schema**：session 元数据表移到 `agent_state.db`（DDL 不变）；**上线前不迁移数据**（新库全新建）。
- **约束遵守**：per-agent 库走嵌入式 Y、非 alembic；不得 `import fleetent.platform.*`；统一经 `db.py` / router 边界。
- **与 #4 的 apply 串行约束**：本切片与 `identity-port`(#4) 都改 `agent_app` 启动接线 → **二者 apply 不可并发**。
- **依赖文档**：data-model.md §5.1/§5.2/§5.7、target-architecture-proposal.md §5。
