# tenant-scoped-db-routing Specification

## Purpose

为 agent 侧 store（首批 = KB）提供单一的"租户作用域"路由入口，使调用方只表达"在某个 tenant 作用域里访问"，由路由解析出该作用域的物理后端句柄（关系库连接 + 向量后端）。抽象支持未来切换为 PostgreSQL per-tenant database 或 RLS，而调用点不变。

## Requirements

### Requirement: 租户作用域路由入口

系统 SHALL 提供路由入口，调用方只表达"在某作用域里访问"，由路由解析出物理后端句柄，MUST NOT 自行拼接物理路径或直接打开库文件。路由 SHALL 暴露两个**平级 typed 解析器**：`tenant_scope(tenant)`（per-tenant 资源，如 KB / 共享记忆）与 `agent_scope(tenant, agent_id)`（per-agent 资源）。返回类型随资源不同——`tenant_scope` 返回 per-tenant 句柄（如 KB 关系库 + 向量后端），`agent_scope` 返回 per-agent 句柄。

#### Scenario: 按主体解析 per-tenant 后端

- **WHEN** 调用方请求 tenant `default` 的 KB 关系库与向量后端
- **THEN** `tenant_scope("default")` 返回该主体对应的 `SQLiteDatabase` 连接与向量后端句柄

#### Scenario: KB 关系库与向量库同源于一个 tenant 作用域

- **WHEN** 同一 tenant 作用域同时取关系库与向量后端
- **THEN** 二者由同一次 `tenant_scope(tenant)` 解析得到，绑定到同一主体

#### Scenario: 两个解析器平级共存

- **WHEN** 调用方需要 per-tenant 资源或 per-agent 资源
- **THEN** 分别经 `tenant_scope(tenant)` 与 `agent_scope(tenant, agent_id)` 取得，二者平级、不互相嵌套

### Requirement: 可换后端抽象

路由后端 SHALL 可插拔：当下 SQLite 后端把 tenant 作用域映射到 `<tenant>/` 目录下的物理文件；后端实现 MUST 可替换为其它实现（如将来 PostgreSQL per-tenant database 或 RLS），而调用点不变。

#### Scenario: SQLite 后端映射到主体目录文件

- **WHEN** 在 SQLite 后端下解析 tenant `T` 的 KB 关系库
- **THEN** 连接指向 `T` 主体目录下的 KB 库文件，物理上不触及其它主体的库

#### Scenario: 切换后端不改调用点

- **WHEN** 后端实现被替换
- **THEN** 调用方仍只通过 `scope(tenant)` 取后端，调用代码无需改动

### Requirement: agent 侧 store 连接来自路由

agent 侧 store（首批 = KB）SHALL 从路由获取连接；模块 MUST NOT 通过 `create_database(settings.database_url)` 等方式自连接全局库。系统 SHALL 提供护栏测试断言此约束。

#### Scenario: KnowledgeStore 经构造注入路由连接

- **WHEN** 构造 `KnowledgeStore`
- **THEN** 其 `database` 由路由提供，而非模块内部自连接

#### Scenario: 护栏捕获自连接旁路

- **WHEN** KB 模块出现 `create_database(...settings...)` 之类的自连接路径
- **THEN** 护栏测试失败并指出该旁路

### Requirement: 单主体作用域先行

本阶段 SHALL 仅支持单主体 `default` 作用域：`tenant_scope("default")` 与 `agent_scope("default", agent_id)` 返回单一后端；多主体 per-tenant 目录 fan-out 不在本切片（留 3d）。抽象 MUST 已就位，使后续启用多主体时调用点不变。

#### Scenario: default 作用域返回单一后端

- **WHEN** 解析 `tenant_scope("default")` 或 `agent_scope("default", agent_id)`
- **THEN** 返回单一主体下的后端句柄，不做多主体目录展开

### Requirement: agent 作用域与 per-agent 库布局

`agent_scope(tenant, agent_id)` SHALL 返回 `AgentScope{state_db, vector_backend}`——该 agent 私有的关系库连接与向量后端。SQLite 后端 SHALL 把它映射到 `<tenant>/<agent_id>/agent_state.db`（关系真相源）与 `<tenant>/<agent_id>/agent_vectors.db`（向量），目录 `<tenant>/<agent_id>/` 的包含关系 MUST 只活在后端路径计算里、不暴露给调用点。

#### Scenario: agent 作用域解析到 per-agent 文件

- **WHEN** 在 SQLite 后端解析 `agent_scope(T, A)`
- **THEN** `state_db` 指向 `<T>/<A>/agent_state.db`、`vector_backend` 指向 `<T>/<A>/agent_vectors.db`，物理上不触及其它 agent 或主体的库

#### Scenario: 调用点不拼目录

- **WHEN** 调用方需要某 agent 的关系库
- **THEN** 只调 `agent_scope(tenant, agent_id).state_db`，不感知 `<tenant>/<agent_id>/` 目录结构

### Requirement: tenant_id 列保留为可换后端接缝

KB 表 SHALL 保留 `tenant_id`/`kb_id` 列。SQLite 文件路由忽略 `tenant_id`（文件本身即主体边界）；将来 RLS 后端 MUST 能按 `tenant_id` 列做行级强制。该列不得因物理分库而删除。

#### Scenario: 物理分库后列仍在

- **WHEN** KB 关系库按主体路由到独立文件
- **THEN** 表结构仍含 `tenant_id`/`kb_id` 列（供可换后端 / RLS 使用）
