## MODIFIED Requirements

### Requirement: 租户作用域路由入口

系统 SHALL 提供路由入口，调用方只表达"在某作用域里访问"，由路由解析出物理后端句柄，MUST NOT 自行拼接物理路径或直接打开库文件。路由 SHALL 暴露两个**平级 typed 解析器**：`tenant_scope(tenant)`（per-tenant 资源，**仅 KB**）与 `agent_scope(tenant, agent_id)`（per-agent 资源，含 agent state、agent 向量）。返回类型随资源不同——`tenant_scope` 返回 per-tenant 句柄（KB 关系库 + 向量后端），`agent_scope` 返回 per-agent 句柄（agent state 关系库 / agent 向量）。

**agent memory 的关系数据 SHALL 存于 `agent_state.db`（`agent_memory_items` 表）**——`agent_scope` MUST NOT 暴露 agent memory 的关系库 open（无 `open_agent_memory_db` / `open_agent_memory_db_ro`）。**agent memory 的向量 SHALL 与 user memory 向量共用 `agent_scope` 返回的单一 per-agent 向量后端**（`agent_vectors.db`），按 namespace 区分（user memory `mem:{user_id}`、agent memory `agentmem:`）——不再有独立的 `agent_memory_vectors.db` 与单独的 `agent_memory_vector_backend`。

#### Scenario: 按主体解析 per-tenant 后端

- **WHEN** 调用方请求 tenant `default` 的 KB 关系库与向量后端
- **THEN** `tenant_scope("default")` 返回该主体对应的 `SQLiteDatabase` 连接与向量后端句柄

#### Scenario: agent memory 关系数据走 agent_state.db

- **WHEN** 调用方需要读写 agent memory 关系记录（`agent_memory_items`）
- **THEN** 经 `agent_scope(tenant, agent_id)` 取得的 **agent_state 关系库**句柄访问；`agent_scope` MUST NOT 提供独立的 agent memory 关系库 open

#### Scenario: agent memory 与 user memory 向量共用单一 per-agent 后端

- **WHEN** 调用方需要 agent memory 或 user memory 的向量后端
- **THEN** 二者经 `agent_scope(tenant, agent_id)` 取得**同一个** per-agent 向量后端（`agent_vectors.db`），按 namespace（`mem:` / `agentmem:`）隔离；不存在独立的 `agent_memory_vectors.db`

#### Scenario: 两个解析器平级共存

- **WHEN** 调用方需要 per-tenant 资源（KB）或 per-agent 资源（agent state / agent memory）
- **THEN** 分别经 `tenant_scope(tenant)` 与 `agent_scope(tenant, agent_id)` 取得，二者平级、不互相嵌套

### Requirement: agent 作用域与 per-agent 库布局

`agent_scope(tenant, agent_id)` SHALL 返回 `AgentScope{state_db, vector_backend}`——该 agent 私有的关系库连接与**单一**向量后端。SQLite 后端 SHALL 把它映射到 `tenants/<tenant>/agents/<agent_id>/data/agent_state.db` 与 `agent_vectors.db`（agent memory 关系数据在 `agent_state.db` 的 `agent_memory_items`，无独立 `agent_memory.db`；agent memory 向量与 user memory 向量同在 `agent_vectors.db`，无独立 `agent_memory_vectors.db`）。agent home 已经限定 agent 作用域，data 目录内 MUST NOT 再嵌套 `<tenant>/<agent_id>/`。

#### Scenario: agent 作用域解析到拍平 per-agent 文件

- **WHEN** 在 SQLite 后端解析 `agent_scope(T, A)`
- **THEN** `state_db` 指向 `tenants/T/agents/A/data/agent_state.db`
- **AND** `vector_backend` 指向 `tenants/T/agents/A/data/agent_vectors.db`（容 `mem:` 与 `agentmem:` namespace）
- **AND** 不存在 `agent_memory_vectors.db`
- **AND** 物理上不触及其它 agent 或主体的库
