## Why

持久层 #3 给 KB 搭好了 per-tenant 路由的架子——`tenant_scope(tenant)` 提供 `KbScope{kb_db, kb_vector_backend}`,agent boot 也 `open_kb_db(KB_MIGRATIONS)` 建出 `<tenant>/kb.db`——但**没接通**:

- **关系库未接**:`knowledge_base.runtime._database()` 写死 `create_database(Settings().database_url)`,KB 所有读写落**默认/管理库**,不是 per-tenant `kb.db`;`open_kb_db` 的句柄在 boot 里**被丢弃**(无 `set_database`)。这**违反 `tenant-scoped-db-routing` 已有要求**「agent 侧 store 从路由取连接、禁自连 Settings」。
- **向量库未接**:KB 检索走**全局 `vector_store` + namespace**(`knowledge_namespace(tenant_id,kb_id)`),不是 `KbScope.kb_vector_backend` 的 per-tenant `kb_vectors.db`——多租户无物理隔离。
- **图谱/状态表不在 kb.db**:`kb_entities`/`kb_entity_mentions`/`kb_relations`/`knowledge_connector_status` 只在 **alembic(管理库)**,没 lift 进 `core/migrations.py`(KB_MIGRATIONS 现仅核心 5 表)。图谱因此实际读管理库——单租户能跑、多租户跨主体。
- `kb_extraction_runs`:只写审计、从不读回(graph_search 不依赖),冗余。

## What Changes

把 KB 的 per-tenant 路由(**关系 + 向量**)接通,并补齐 kb.db 的表:

- **接线注入口**:`knowledge_base.runtime` 加 `set_database()` + 向量 backend 注入口(照 `memory.set_state_db` 模式)。
- **两上下文都接**:
  - **agent 读**(`agent_app` boot):接住 `open_kb_db` 句柄 + `KbScope.kb_vector_backend` → 注入 KB runtime,使 retrieval/graph_search 读本租户 `kb.db` / `kb_vectors.db`。
  - **platform 写**(`kb_admin_api` / `admin_cli` 的 ingest/sync/extraction):按 tenant 解析 `tenant_scope` → 注入 → 写本租户 `kb.db` / `kb_vectors.db`。
- **去自连旁路**:`runtime._database()`、`operations.py` 的 `default_database()`、`graph_search` 的 `Settings()` fallback 全改用注入句柄;向量去掉"全局 vector_store + namespace",改用注入的 `kb_vector_backend`。
- **lift 图谱 + 状态进 KB_MIGRATIONS**:`kb_entities` / `kb_entity_mentions` / `kb_relations`(删死列 `extraction_run_id`)、`knowledge_connector_status` 原样 lift 进 `core/migrations.py`,使 kb.db 具备全部 KB 关系表。
- **砍 `kb_extraction_runs`**:抽取仍跑、仍产 entities/mentions/relations,但不持久化 run-log(返回值同步给调用方);若要运行审计 → 发 observability trace event。
- **drop alembic 的 KB 定义**:管理库不再建 KB 表(`knowledge_bases`/`documents`/`chunks`/`chunks_fts`/`source_states`/`kb_entities`/`mentions`/`relations`/`connector_status`/`extraction_runs`),新 alembic 迁移 forward-drop(镜像 074)。

不在本切片:KB 数据迁移(无存量真实数据,新建/重 ingest);`agent_kbs` / `kb_connectors`(平台侧配置,留管理库);KB 自进化 remediation(独立 change)。

## Capabilities

### New Capabilities
<!-- 无;落实/扩展既有能力 -->

### Modified Capabilities
- `tenant-scoped-db-routing`: 落实并扩展「agent 侧 store 连接来自路由」——KB 的**关系连接(`kb_db`)与向量后端(`kb_vector_backend`)**均经 `tenant_scope` 注入,**agent 读路径与 platform 写(ingest)路径都接**;去掉 `runtime._database()` 自连 Settings、retrieval 用全局 `vector_store+namespace` 的旁路。
- `embedded-schema-migration`: KB 的 `MIGRATIONS` 由"仅核心 5 表"扩为**全部 KB 关系表**(核心 5 + 图谱 3 + `knowledge_connector_status`,`kb_extraction_runs` 不建);管理库 alembic 不再定义任何 KB 表(forward-drop)。

## Impact

- **代码**:`knowledge_base/runtime.py`(注入口 + 去自连)、`knowledge_base/operations.py`(去 `default_database`)、`knowledge_base/retrieval/*`(graph_search 去 Settings fallback;search 用注入向量后端而非全局)、`knowledge_base/core/migrations.py`(lift 图谱3+connector_status)、`knowledge_base/extraction_store.py`(砍 extraction_runs)、`runtime/agent_app.py`(接 KB 关系+向量句柄)、`platform/knowledge_base_management/kb_admin_api.py` + `platform/admin_cli/kb_connectors.py`(ingest/sync 按 tenant 注入)、新 alembic 迁移 drop KB 表。
- **owned tables**:`kb.db`(per-tenant)= 核心5 + 图谱3 + connector_status;`kb_vectors.db`(per-tenant)= KB 向量;管理库不再含 KB 表;`kb_extraction_runs` 退场。
- **config namespace**:无;**cross-module**:`tenant_router`(KbScope)、`vector_store`、`db.py`。
- **migration/shim**:KB_MIGRATIONS append 图谱/connector DDL;alembic forward-drop KB 表;**无数据迁移**(无存量数据)。
- **验证基线**:多租户下 T1 的 agent 进程只读 T1 的 `kb.db`/`kb_vectors.db`,物理够不到 T2;无 platform、管理库无 KB 表时,KB 读写仍落 per-tenant kb.db。
