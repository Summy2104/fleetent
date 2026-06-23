## MODIFIED Requirements

### Requirement: 租户作用域路由入口

系统 SHALL 提供路由入口，调用方只表达"在某作用域里访问"，由路由解析出物理后端句柄，MUST NOT 自行拼接物理路径或直接打开库文件。路由 SHALL 暴露两个**平级 typed 解析器**：`tenant_scope(tenant)`（per-tenant 资源，**仅 KB**）与 `agent_scope(tenant, agent_id)`（per-agent 资源，含 agent state、agent 向量、**agent memory**）。返回类型随资源不同——`tenant_scope` 返回 per-tenant 句柄（KB 关系库 + 向量后端），`agent_scope` 返回 per-agent 句柄（agent state / 向量 / agent memory）。**agent memory 是 per-agent 资源，MUST NOT 经 `tenant_scope` 解析**（不再有 per-tenant 的 `open_shared_memory_db`）。

#### Scenario: 按主体解析 per-tenant 后端

- **WHEN** 调用方请求 tenant `default` 的 KB 关系库与向量后端
- **THEN** `tenant_scope("default")` 返回该主体对应的 `SQLiteDatabase` 连接与向量后端句柄

#### Scenario: agent memory 经 agent_scope 解析

- **WHEN** 调用方请求某 agent 的 agent memory 库
- **THEN** 经 `agent_scope(tenant, agent_id)` 取得 per-agent 句柄；`tenant_scope` MUST NOT 提供 agent memory

#### Scenario: 两个解析器平级共存

- **WHEN** 调用方需要 per-tenant 资源（KB）或 per-agent 资源（agent state / agent memory）
- **THEN** 分别经 `tenant_scope(tenant)` 与 `agent_scope(tenant, agent_id)` 取得，二者平级、不互相嵌套
