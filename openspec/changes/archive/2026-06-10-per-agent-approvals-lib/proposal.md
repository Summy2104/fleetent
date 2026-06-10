## Why

持久层 #3 的 **3b-4**：把 `approvals`（审批请求 + 门状态）迁入 per-agent `agent_state.db`（`agent_scope` + 嵌入式 Y），并完成**双权威清理**——change A 已把 approvals 写侧移到 agent 侧 `governance/approval_store`，但 alembic 仍留着 `approvals` 的孤立定义（060 等）；本切片 **drop 管理库 alembic 的 approvals 定义**，使 agent 侧 approval_store 成唯一真相源。

> 假设 3b-1 的 `agent_scope` / per-agent `MIGRATIONS` 契约；apply 前复核。platform 对 approvals 的**只读投影**遵 target-arch §7，其**实现依赖 3d 的只读 router**，故本切片只立"agent 侧唯一真相源"，投影实现留 3d。

## What Changes

- `governance/approval_store.py`（`approvals` 表）+ `approval_allowlist_store.py` 的 DDL lift 进 per-agent 库 `MIGRATIONS`；连接从 `ensure_schema(db_path)` 改为经 `agent_scope(tenant, agent_id).state_db` + migrate-on-open。
- **drop 管理库 alembic 的 `approvals` 孤立定义**（新增 alembic 迁移）——agent 侧 approval_store 唯一真相源（接 R1：agent 全权写、platform 只读投影）。
- `agent_app` 审批相关接线到 agent_scope。
- 单主体 `default` 先。

不在本切片：platform 只读投影**实现**（依赖 3d 只读 router）；fan-out（3d）；其余 per-agent store（已在 3b-1/2/3）。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `agent-db-schema-self-init`: 新增「approvals 经 per-agent Y + `agent_scope` 建 schema、agent 侧 approval_store 为唯一真相源、管理库 alembic 不再定义 approvals」要求；这是 per-agent 迁移链末——同时 **REMOVE** 旧「Each agent-side store exposes ensure_schema」要求（至此 KB/session/traces/reflection/memory/approvals 均已迁 Y，无 agent 侧 store 再 ensure_schema-into-global）。

## Impact

- **代码**：`governance/approval_store.py`、`approval_allowlist_store.py`（连接走 agent_scope、DDL lift）；`agent_app` 接线。
- **数据/schema**：approvals 移到 `agent_state.db`；管理库 drop alembic approvals 表（新增迁移）；上线前不迁移数据。
- **约束**：管理库 drop 走 alembic；per-agent 走 Y；不 import platform。
- **依赖**：3b-1（agent_scope）；3d（只读投影实现）后置。**与 3b-1/#4 同改 agent_app → 串行排 3b-1 后。**
- **文档**：data-model.md §5.1/§5.5（R1 审批契约）、target-arch §7（只读投影）。
