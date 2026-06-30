## MODIFIED Requirements

### Requirement: 可换后端抽象

路由后端 SHALL 可插拔：当下 SQLite 后端把 tenant 作用域映射到 `tenants/<tenant>/` 下的物理文件；后端实现 MUST 可替换为其它实现（如将来 PostgreSQL per-tenant database 或 RLS），而调用点不变。per-tenant KB 文件 SHALL 归组于 `tenants/<tenant>/kb/data/` 子目录。

#### Scenario: SQLite 后端映射到 tenant-first 主体目录文件
- **WHEN** 在 SQLite 后端下解析 tenant `T` 的 KB 关系库
- **THEN** 连接指向 `tenants/T/kb/data/kb.db`
- **AND** 物理上不触及其它主体的库

#### Scenario: 切换后端不改调用点
- **WHEN** 后端实现被替换
- **THEN** 调用方仍只通过 `tenant_scope(tenant)` 或 `agent_scope(tenant, agent)` 取后端
- **AND** 调用代码无需改动

### Requirement: agent 侧 store 连接来自路由

agent 侧 store（首批 = KB）SHALL 从路由获取连接；模块 MUST NOT 通过 `create_database(settings.database_url)` 等方式自连接全局库。系统 SHALL 提供护栏测试断言此约束。

KB 的**关系连接**（`kb_db`）与**向量后端**（`kb_vector_backend`）SHALL 均经 `tenant_scope(tenant)` 的 `KbScope` 注入到 `knowledge_base.runtime`（提供 `set_database` 与向量后端注入口），由注入句柄读写本租户 `<tenant>/kb/data/kb.db` 与 `<tenant>/kb/data/kb_vectors.db`。`runtime._database()` MUST NOT 再 `create_database(Settings().database_url)` 自连默认库；KB 检索 MUST NOT 再用“全局 `vector_store` + `knowledge_namespace`”旁路，而经注入的 `kb_vector_backend`。注入 SHALL 在**两个上下文**完成：**agent 读路径**（`agent_app` boot，供 retrieval / graph_search）与**platform 写路径**（ingest / connector sync / 抽取，供写本租户 `kb/data/kb.db`）。

#### Scenario: KnowledgeStore 经构造注入路由连接

- **WHEN** 构造 `KnowledgeStore`
- **THEN** 其 `database` 由路由提供，而非模块内部自连接

#### Scenario: 护栏捕获自连接旁路

- **WHEN** KB 模块出现 `create_database(...settings...)` 之类的自连接路径
- **THEN** 护栏测试失败并指出该旁路

#### Scenario: KB runtime 经注入读本租户 kb.db

- **WHEN** agent 检索或 platform ingest 访问 KB 关系数据
- **THEN** 经注入的 `kb_db`（来自 `tenant_scope`）读写 `<tenant>/kb/data/kb.db`
- **AND** `runtime._database()` 不再自连 `Settings().database_url`

#### Scenario: KB 向量经注入的 per-tenant 后端

- **WHEN** KB 检索或 ingest 访问向量
- **THEN** 经注入的 `kb_vector_backend`（本租户 `<tenant>/kb/data/kb_vectors.db`）访问向量
- **AND** 不再走全局 `vector_store` + namespace 旁路

#### Scenario: 多租户物理隔离

- **WHEN** 主体 `T1` 的 agent 进程检索 KB
- **THEN** 只触及 `<T1>/kb/data/kb.db` 与 `<T1>/kb/data/kb_vectors.db`
- **AND** 物理上够不到 `<T2>` 的 KB 关系库或向量库

#### Scenario: agent 读与 platform 写两上下文都经路由

- **WHEN** agent 检索（读）或 platform ingest/sync（写）各自访问某租户 KB
- **THEN** 两者都经 `tenant_scope` 解析到同一 `<tenant>/kb/data/kb.db`
- **AND** 无一方落默认库或管理库

### Requirement: KB per-tenant 文件分组于 kb/ 子目录

per-tenant 的 KB 关系库与向量库 SHALL 归组于 `tenants/<tenant>/kb/data/` 子目录(`kb/data/kb.db`、`kb/data/kb_vectors.db`,连同 SQLite 的 `-wal`/`-shm`),而非松散置于租户根或 `kb/` 根。`kb/` 根 SHALL 只承载 standalone KB 服务的配置面(`kb-service.yaml`、`.env`),`kb/data/` 承载数据/读面,二者分层与 agent home 同构。该 `kb/data/` 目录 SHALL 可作为**单一单元**被搬迁或挂载;容器部署下 node SHALL 把整个 `kb/data/` 目录(而非整个 `kb/`、亦非单个文件)以只读挂入 agent 容器,使 `-wal`/`-shm` 一并可见、agent 读到一致快照,同时把 `kb/` 根的 `.env`(KB embedding / connector secret)挡在 agent 读面之外。

`ensure_tenant_kb_dir` 等 provision 路径 SHALL **仅幂等建立 `kb/data/` 目录**,SHALL NOT 自动搬迁任何 legacy 旧址布局(租户根扁平 `tenants/<tenant>/kb.db`、或 `kb/` 根 `tenants/<tenant>/kb/kb.db`)的数据——采 clean-break:存量旧址文件保持原地,如需保留由运维自行移入 `kb/data/` 或删除。

#### Scenario: KB 文件位于 kb/data/ 子目录
- **WHEN** 解析某租户的 KB 关系库与向量库
- **THEN** 物理文件位于 `tenants/<tenant>/kb/data/kb.db` 与 `tenants/<tenant>/kb/data/kb_vectors.db`
- **AND** 租户根与 `kb/` 根都不直接含 `kb.db` / `kb_vectors.db`

#### Scenario: node 只读挂载 kb/data/ 维持 WAL 一致并隔离 secret
- **WHEN** node 容器为 agent 提供 KB 只读访问
- **THEN** node 只读挂载整个 `tenants/<tenant>/kb/data/` 目录(含 `-wal`/`-shm`),而非整个 `kb/`、亦非单个 `kb.db` 文件
- **AND** agent 读到的 KB 快照不滞后于已提交写入
- **AND** `kb/` 根的 `kb-service.yaml` / `.env` 不出现在 agent 容器的挂载读面内

#### Scenario: legacy 旧址不自动迁移
- **WHEN** 存量环境的 KB 文件位于 legacy 旧址(`tenants/<tenant>/kb.db` 租户根、或 `tenants/<tenant>/kb/kb.db` 的 `kb/` 根)、而 `kb/data/` 不存在
- **THEN** provision 仅幂等建立空的 `kb/data/`,旧址文件保持原地、不被自动搬迁
- **AND** 该取舍为 clean-break:需保留的数据由运维自行移入 `kb/data/`
