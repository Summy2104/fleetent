# tenant-scoped-db-routing Specification

## Purpose

为 agent 侧 store（首批 = KB）提供单一的"租户作用域"路由入口，使调用方只表达"在某个 tenant 作用域里访问"，由路由解析出该作用域的物理后端句柄（关系库连接 + 向量后端）。抽象支持未来切换为 PostgreSQL per-tenant database 或 RLS，而调用点不变。
## Requirements
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

### Requirement: 可换后端抽象

路由后端 SHALL 可插拔：当下 SQLite 后端把 tenant 作用域映射到 `tenants/<tenant>/` 下的物理文件；后端实现 MUST 可替换为其它实现（如将来 PostgreSQL per-tenant database 或 RLS），而调用点不变。per-tenant KB 文件 SHALL 归组于 `tenants/<tenant>/kb/` 子目录。

#### Scenario: SQLite 后端映射到 tenant-first 主体目录文件
- **WHEN** 在 SQLite 后端下解析 tenant `T` 的 KB 关系库
- **THEN** 连接指向 `tenants/T/kb/kb.db`
- **AND** 物理上不触及其它主体的库

#### Scenario: 切换后端不改调用点
- **WHEN** 后端实现被替换
- **THEN** 调用方仍只通过 `tenant_scope(tenant)` 或 `agent_scope(tenant, agent)` 取后端
- **AND** 调用代码无需改动

### Requirement: agent 侧 store 连接来自路由

agent 侧 store（首批 = KB）SHALL 从路由获取连接；模块 MUST NOT 通过 `create_database(settings.database_url)` 等方式自连接全局库。系统 SHALL 提供护栏测试断言此约束。

KB 的**关系连接**（`kb_db`）与**向量后端**（`kb_vector_backend`）SHALL 均经 `tenant_scope(tenant)` 的 `KbScope` 注入到 `knowledge_base.runtime`（提供 `set_database` 与向量后端注入口），由注入句柄读写本租户 `<tenant>/kb/kb.db` 与 `<tenant>/kb/kb_vectors.db`。`runtime._database()` MUST NOT 再 `create_database(Settings().database_url)` 自连默认库；KB 检索 MUST NOT 再用“全局 `vector_store` + `knowledge_namespace`”旁路，而经注入的 `kb_vector_backend`。注入 SHALL 在**两个上下文**完成：**agent 读路径**（`agent_app` boot，供 retrieval / graph_search）与**platform 写路径**（ingest / connector sync / 抽取，供写本租户 `kb/kb.db`）。

#### Scenario: KnowledgeStore 经构造注入路由连接

- **WHEN** 构造 `KnowledgeStore`
- **THEN** 其 `database` 由路由提供，而非模块内部自连接

#### Scenario: 护栏捕获自连接旁路

- **WHEN** KB 模块出现 `create_database(...settings...)` 之类的自连接路径
- **THEN** 护栏测试失败并指出该旁路

#### Scenario: KB runtime 经注入读本租户 kb.db

- **WHEN** agent 检索或 platform ingest 访问 KB 关系数据
- **THEN** 经注入的 `kb_db`（来自 `tenant_scope`）读写 `<tenant>/kb/kb.db`
- **AND** `runtime._database()` 不再自连 `Settings().database_url`

#### Scenario: KB 向量经注入的 per-tenant 后端

- **WHEN** KB 检索或 ingest 访问向量
- **THEN** 经注入的 `kb_vector_backend`（本租户 `<tenant>/kb/kb_vectors.db`）访问向量
- **AND** 不再走全局 `vector_store` + namespace 旁路

#### Scenario: 多租户物理隔离

- **WHEN** 主体 `T1` 的 agent 进程检索 KB
- **THEN** 只触及 `<T1>/kb/kb.db` 与 `<T1>/kb/kb_vectors.db`
- **AND** 物理上够不到 `<T2>` 的 KB 关系库或向量库

#### Scenario: agent 读与 platform 写两上下文都经路由

- **WHEN** agent 检索（读）或 platform ingest/sync（写）各自访问某租户 KB
- **THEN** 两者都经 `tenant_scope` 解析到同一 `<tenant>/kb/kb.db`
- **AND** 无一方落默认库或管理库

### Requirement: agent 作用域与 per-agent 库布局

`agent_scope(tenant, agent_id)` SHALL 返回 `AgentScope{state_db, vector_backend}`——该 agent 私有的关系库连接与**单一**向量后端。SQLite 后端 SHALL 把它映射到 `tenants/<tenant>/agents/<agent_id>/data/agent_state.db` 与 `agent_vectors.db`（agent memory 关系数据在 `agent_state.db` 的 `agent_memory_items`，无独立 `agent_memory.db`；agent memory 向量与 user memory 向量同在 `agent_vectors.db`，无独立 `agent_memory_vectors.db`）。agent home 已经限定 agent 作用域，data 目录内 MUST NOT 再嵌套 `<tenant>/<agent_id>/`。

#### Scenario: agent 作用域解析到拍平 per-agent 文件

- **WHEN** 在 SQLite 后端解析 `agent_scope(T, A)`
- **THEN** `state_db` 指向 `tenants/T/agents/A/data/agent_state.db`
- **AND** `vector_backend` 指向 `tenants/T/agents/A/data/agent_vectors.db`（容 `mem:` 与 `agentmem:` namespace）
- **AND** 不存在 `agent_memory_vectors.db`
- **AND** 物理上不触及其它 agent 或主体的库

### Requirement: tenant_id 列保留为可换后端接缝

KB 表 SHALL 保留 `tenant_id`/`kb_id` 列。SQLite 文件路由忽略 `tenant_id`（文件本身即主体边界）；将来 RLS 后端 MUST 能按 `tenant_id` 列做行级强制。该列不得因物理分库而删除。

#### Scenario: 物理分库后列仍在

- **WHEN** KB 关系库按主体路由到独立文件
- **THEN** 表结构仍含 `tenant_id`/`kb_id` 列（供可换后端 / RLS 使用）

### Requirement: 多主体 fan-out 与主体来源

`tenant_scope(tenant)` / `agent_scope(tenant, agent_id)` SHALL 按**真实主体**路由到 `<tenant>/` 物理分区（不再固定 `default`）。物理路由的主体 SHALL 取自**运行 agent 的归属主体**（agent 配置 `tenant_id`（`agent_tenant`），来自 agent 配置/materialize），而非请求者 `Principal`。不同主体的库 SHALL 物理分处不同目录，一个 agent 进程 MUST 够不到别主体的库。

#### Scenario: 按 agent 归属主体路由

- **WHEN** 主体 `T1` 的 agent 运行并请求其库
- **THEN** 路由解析到 `<T1>/...`，与 `T2` 的库物理分处不同目录

#### Scenario: 跨主体物理隔离

- **WHEN** `T1` 的 agent 进程尝试访问数据
- **THEN** 只触及 `<T1>/` 下的库，物理上够不到 `<T2>/` 的任何库

### Requirement: 主体目录 provisioning

系统 SHALL 在需要时建立 `tenants/<tenant>/kb/` 与 `tenants/<tenant>/agents/<agent>/data/` 目录结构（node reconcile、standalone init/run，或 router 开库时幂等 lazy 建父目录），使多主体物理分区可用。

#### Scenario: 新主体目录就绪
- **WHEN** 新主体/agent 首次需要其库
- **THEN** 对应 `tenants/<tenant>/kb/` 与 `tenants/<tenant>/agents/<agent>/data/` 目录存在或被幂等建立
- **AND** 库可正常开

### Requirement: KB per-tenant 文件分组于 kb/ 子目录

per-tenant 的 KB 关系库与向量库 SHALL 归组于 `tenants/<tenant>/kb/data/` 子目录(`kb/data/kb.db`、`kb/data/kb_vectors.db`,连同 SQLite 的 `-wal`/`-shm`),而非松散置于租户根或 `kb/` 根。`kb/` 根 SHALL 只承载 standalone KB 服务的配置面(`kb-service.yaml`、`.env`),`kb/data/` 承载数据/读面,二者分层与 agent home 同构。该 `kb/data/` 目录 SHALL 可作为**单一单元**被搬迁或挂载;容器部署下 node SHALL 把整个 `kb/data/` 目录(而非整个 `kb/`、亦非单个文件)以只读挂入 agent 容器,使 `-wal`/`-shm` 一并可见、agent 读到一致快照,同时把 `kb/` 根的 `.env`(KB embedding / connector secret)挡在 agent 读面之外。

#### Scenario: KB 文件位于 kb/data/ 子目录
- **WHEN** 解析某租户的 KB 关系库与向量库
- **THEN** 物理文件位于 `tenants/<tenant>/kb/data/kb.db` 与 `tenants/<tenant>/kb/data/kb_vectors.db`
- **AND** 租户根与 `kb/` 根都不直接含 `kb.db` / `kb_vectors.db`

#### Scenario: node 只读挂载 kb/data/ 维持 WAL 一致并隔离 secret
- **WHEN** node 容器为 agent 提供 KB 只读访问
- **THEN** node 只读挂载整个 `tenants/<tenant>/kb/data/` 目录(含 `-wal`/`-shm`),而非整个 `kb/`、亦非单个 `kb.db` 文件
- **AND** agent 读到的 KB 快照不滞后于已提交写入
- **AND** `kb/` 根的 `kb-service.yaml` / `.env` 不出现在 agent 容器的挂载读面内

