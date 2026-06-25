## MODIFIED Requirements

### Requirement: 租户作用域路由入口

系统 SHALL 提供路由入口，调用方只表达"在某作用域里访问"，由路由解析出物理后端句柄，MUST NOT 自行拼接物理路径或直接打开库文件。路由 SHALL 暴露两个**平级 typed 解析器**：`tenant_scope(tenant)`（per-tenant 资源，**仅 KB**）与 `agent_scope(tenant, agent_id)`（per-agent 资源，含 agent state、agent 向量、**agent memory 向量**）。返回类型随资源不同——`tenant_scope` 返回 per-tenant 句柄（KB 关系库 + 向量后端），`agent_scope` 返回 per-agent 句柄（agent state 关系库 / agent 向量 / agent memory 向量）。

**agent memory 的关系数据 SHALL 存于 `agent_state.db`（`agent_memory_items` 表），不再有独立的 `agent_memory.db` 关系库**——`agent_scope` MUST NOT 暴露 agent memory 的关系库 open（无 `open_agent_memory_db` / `open_agent_memory_db_ro`）。agent memory 的**向量** backend（`agentmem` family）SHALL 仍由 `agent_scope` 提供（独立向量库，与 KB / user-memory 向量按 family 分库）。

#### Scenario: 按主体解析 per-tenant 后端

- **WHEN** 调用方请求 tenant `default` 的 KB 关系库与向量后端
- **THEN** `tenant_scope("default")` 返回该主体对应的 `SQLiteDatabase` 连接与向量后端句柄

#### Scenario: agent memory 关系数据走 agent_state.db

- **WHEN** 调用方需要读写 agent memory 关系记录（`agent_memory_items`）
- **THEN** 经 `agent_scope(tenant, agent_id)` 取得的 **agent_state 关系库**句柄访问；`agent_scope` MUST NOT 提供独立的 agent memory 关系库 open

#### Scenario: agent memory 向量仍按 family 独立

- **WHEN** 调用方需要 agent memory 的向量 backend
- **THEN** 经 `agent_scope(tenant, agent_id)` 取得 `agentmem` family 的向量 backend（独立向量库），与 agent state 关系库分离

#### Scenario: 两个解析器平级共存

- **WHEN** 调用方需要 per-tenant 资源（KB）或 per-agent 资源（agent state / agent memory）
- **THEN** 分别经 `tenant_scope(tenant)` 与 `agent_scope(tenant, agent_id)` 取得，二者平级、不互相嵌套
