## MODIFIED Requirements

### Requirement: 可换后端抽象

路由后端 SHALL 可插拔：当下 SQLite 后端把 tenant 作用域映射到 `tenants/<tenant>/` 下的物理文件；后端实现 MUST 可替换为其它实现（如将来 PostgreSQL per-tenant database 或 RLS），而调用点不变。

#### Scenario: SQLite 后端映射到 tenant-first 主体目录文件
- **WHEN** 在 SQLite 后端下解析 tenant `T` 的 KB 关系库
- **THEN** 连接指向 `tenants/T/kb.db`
- **AND** 物理上不触及其它主体的库

#### Scenario: 切换后端不改调用点
- **WHEN** 后端实现被替换
- **THEN** 调用方仍只通过 `tenant_scope(tenant)` 或 `agent_scope(tenant, agent)` 取后端
- **AND** 调用代码无需改动

### Requirement: agent 作用域与 per-agent 库布局

`agent_scope(tenant, agent_id)` SHALL 返回 `AgentScope{state_db, vector_backend, agent_memory_db, agent_memory_vector_backend}`——该 agent 私有的关系库连接与向量后端。SQLite 后端 SHALL 把它映射到 `tenants/<tenant>/agents/<agent_id>/data/agent_state.db`、`agent_vectors.db`、`agent_memory.db` 与 `agent_memory_vectors.db`。agent home 已经限定 agent 作用域，data 目录内 MUST NOT 再嵌套 `<tenant>/<agent_id>/`。

#### Scenario: agent 作用域解析到拍平 per-agent 文件
- **WHEN** 在 SQLite 后端解析 `agent_scope(T, A)`
- **THEN** `state_db` 指向 `tenants/T/agents/A/data/agent_state.db`
- **AND** `vector_backend` 指向 `tenants/T/agents/A/data/agent_vectors.db`
- **AND** `agent_memory_db` 指向 `tenants/T/agents/A/data/agent_memory.db`
- **AND** 物理上不触及其它 agent 或主体的库

#### Scenario: agent data 不再内嵌 tenant/agent 目录
- **WHEN** `_init_agent_db_schema` 为 tenant `T` 的 agent `A` 初始化 DB
- **THEN** 不创建 `tenants/T/agents/A/data/T/A/`
- **AND** 所有 per-agent DB 文件位于 `tenants/T/agents/A/data/` 直属层级

#### Scenario: 调用点不拼目录
- **WHEN** 调用方需要某 agent 的关系库
- **THEN** 只调 `agent_scope(tenant, agent_id).state_db`
- **AND** 不感知 tenant-first 物理目录结构

### Requirement: 主体目录 provisioning

系统 SHALL 在需要时建立 `tenants/<tenant>/` 与 `tenants/<tenant>/agents/<agent>/data/` 目录结构（node reconcile、standalone init/run，或 router 开库时幂等 lazy 建父目录），使多主体物理分区可用。

#### Scenario: 新主体目录就绪
- **WHEN** 新主体/agent 首次需要其库
- **THEN** 对应 `tenants/<tenant>/agents/<agent>/data/` 目录存在或被幂等建立
- **AND** 库可正常开
