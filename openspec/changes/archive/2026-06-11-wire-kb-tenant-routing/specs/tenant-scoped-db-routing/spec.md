## MODIFIED Requirements

### Requirement: agent 侧 store 连接来自路由

agent 侧 store（首批 = KB）SHALL 从路由获取连接;模块 MUST NOT 通过 `create_database(settings.database_url)` 等方式自连接全局库。系统 SHALL 提供护栏测试断言此约束。

KB 的**关系连接**(`kb_db`)与**向量后端**(`kb_vector_backend`)SHALL 均经 `tenant_scope(tenant)` 的 `KbScope` 注入到 `knowledge_base.runtime`(提供 `set_database` / 向量后端注入口),由注入句柄读写本租户 `<tenant>/kb.db` 与 `<tenant>/kb_vectors.db`。`runtime._database()` MUST NOT 再 `create_database(Settings().database_url)` 自连默认库;KB 检索 MUST NOT 再用"全局 `vector_store` + `knowledge_namespace`"旁路,而经注入的 `kb_vector_backend`。注入 SHALL 在**两个上下文**完成:**agent 读路径**(`agent_app` boot,供 retrieval / graph_search)与 **platform 写路径**(ingest / connector sync / 抽取,供写本租户 kb.db)。

#### Scenario: KnowledgeStore 经构造注入路由连接
- **WHEN** 构造 `KnowledgeStore`
- **THEN** 其 `database` 由路由提供,而非模块内部自连接

#### Scenario: 护栏捕获自连接旁路
- **WHEN** KB 模块出现 `create_database(...settings...)` 之类的自连接路径
- **THEN** 护栏测试失败并指出该旁路

#### Scenario: KB runtime 经注入读本租户 kb.db
- **WHEN** agent 检索或 platform ingest 访问 KB 关系数据
- **THEN** 经注入的 `kb_db`(来自 `tenant_scope`)读写 `<tenant>/kb.db`,`runtime._database()` 不再自连 `Settings().database_url`

#### Scenario: KB 向量经注入的 per-tenant 后端
- **WHEN** KB 检索或 ingest 访问向量
- **THEN** 经注入的 `kb_vector_backend`(本租户 `kb_vectors.db`)而非全局 `vector_store` + namespace

#### Scenario: 多租户物理隔离
- **WHEN** 主体 `T1` 的 agent 进程检索 KB
- **THEN** 只触及 `<T1>/kb.db` 与 `<T1>/kb_vectors.db`,物理上够不到 `<T2>` 的 KB 关系库/向量库

#### Scenario: agent 读 + platform 写两上下文都经路由
- **WHEN** agent 检索(读)或 platform ingest/sync(写)各自访问某租户 KB
- **THEN** 两者都经 `tenant_scope` 解析到同一 `<tenant>/kb.db`,无一方落默认/管理库
