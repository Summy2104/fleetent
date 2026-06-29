## MODIFIED Requirements

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

### Requirement: 主体目录 provisioning

系统 SHALL 在需要时建立 `tenants/<tenant>/kb/` 与 `tenants/<tenant>/agents/<agent>/data/` 目录结构（node reconcile、standalone init/run，或 router 开库时幂等 lazy 建父目录），使多主体物理分区可用。

#### Scenario: 新主体目录就绪
- **WHEN** 新主体/agent 首次需要其库
- **THEN** 对应 `tenants/<tenant>/kb/` 与 `tenants/<tenant>/agents/<agent>/data/` 目录存在或被幂等建立
- **AND** 库可正常开

## ADDED Requirements

### Requirement: KB per-tenant 文件分组于 kb/ 子目录

per-tenant 的 KB 关系库与向量库 SHALL 归组于 `tenants/<tenant>/kb/` 子目录(`kb/kb.db`、`kb/kb_vectors.db`,连同 SQLite 的 `-wal`/`-shm`),而非松散置于租户根。该 `kb/` 目录 SHALL 可作为**单一单元**被搬迁或挂载;容器部署下 node SHALL 把整个 `kb/` 目录(而非单个文件)挂入 agent 容器,使 `-wal`/`-shm` 一并可见、agent 读到一致快照。遇到 legacy 扁平布局(`tenants/<tenant>/kb.db` 直接位于租户根)时,系统 SHALL 幂等迁移其至 `kb/` 下。

#### Scenario: KB 文件位于 kb/ 子目录
- **WHEN** 解析某租户的 KB 关系库与向量库
- **THEN** 物理文件位于 `tenants/<tenant>/kb/kb.db` 与 `tenants/<tenant>/kb/kb_vectors.db`
- **AND** 租户根不再直接含 `kb.db` / `kb_vectors.db`

#### Scenario: node 挂载 kb/ 整目录修复 WAL 一致性
- **WHEN** node 容器为 agent 提供 KB 只读访问
- **THEN** node 挂载整个 `tenants/<tenant>/kb/` 目录(含 `-wal`/`-shm`),而非单个 `kb.db` 文件
- **AND** agent 读到的 KB 快照不滞后于已提交写入

#### Scenario: legacy 扁平布局幂等迁移
- **WHEN** 存量环境的 `kb.db` / `kb_vectors.db` 直接位于 `tenants/<tenant>/` 根且 `kb/` 尚不存在
- **THEN** 系统建立 `kb/` 并把这些文件(含 `-wal`/`-shm`)移入
- **AND** 迁移幂等,重复执行不破坏已迁移布局
