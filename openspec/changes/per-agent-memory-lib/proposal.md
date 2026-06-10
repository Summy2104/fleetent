## Why

持久层 #3 的 **3b-3**：把 `memory`（user memory）store 迁入 per-agent `agent_state.db`（`agent_scope` + 嵌入式 Y），并落地 **R2-叉2**——记忆隔离改由 **per-agent 物理库**承担，移除 `memory_namespace` / memory 操作的 `namespace` 第二参（`mem:{user_id}` 即足）。

> 假设 3b-1 的 `agent_scope` / `agent_state.db` / per-agent `MIGRATIONS` 契约；apply 前复核。

## What Changes

- `memory/store.py`（`memory_items` 表）DDL lift 进 per-agent 库 `MIGRATIONS`；连接走 `agent_scope(tenant, agent_id).state_db` + migrate-on-open；`agent_app` 接线。
- **去 namespace 第二参（R2-叉2）**：`vector_store.memory_namespace(user_id, namespace="default")` → `memory_namespace(user_id)`（`mem:{user_id}`）；memory `search` / `extract_and_update` 等的 `namespace` 第二参移除。**agent 隔离由"每 agent 一个 `agent_state.db`"提供，不再靠 namespace 区分列/串。**
- `memory_items` 不再需要 `namespace` 列（R2-叉2；新库全新建即无此列）。

不在本切片：traces/reflection（3b-2）、approvals（3b-4）、shared memory（3c，注意 shared 仍用 `shared:` namespace，不受本切片影响）；fan-out（3d）。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `agent-db-schema-self-init`: 新增「memory 经 per-agent Y + `agent_scope` 建 schema」要求——`memory/store.py` 不再 `ensure_schema`-into-global。
- `memory-layer`: 新增「记忆隔离经 per-agent 物理库」要求——agent 隔离由每 agent 一个 `agent_state.db` 提供；`memory_namespace` 与 memory 操作移除 `namespace` 第二参（`mem:{user_id}`）；`memory_items` 无 `namespace` 列。user-scoping（按 `user_id`）不变。

## Impact

- **代码**：`memory/store.py`（连接走 agent_scope、DDL lift、去 namespace 列）；`vector_store/namespaces.py`（`memory_namespace` 去第二参）；memory `search`/`extract_and_update` 签名去 `namespace`；调用点（`long_term_ctx` 等）同步。
- **数据/schema**：`memory_items` 移到 `agent_state.db`、无 `namespace` 列；上线前不迁移数据（新库全新建——R2-叉2 的"搬迁键难题"随之消失）。
- **约束**：per-agent Y、非 alembic；不 import platform；named params。
- **依赖**：3b-1。**与 3b-1/#4 同改 agent_app → 串行排 3b-1 后。**
- **文档**：data-model.md §5.1/§5.2/§5.7（向量 `mem:{user_id}`）、roadmap R2-叉2。
