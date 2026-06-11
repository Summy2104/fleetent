## Context

#3 给 KB 搭了 per-tenant 路由架子但没接通(复核已确认):
- `knowledge_base.runtime._database()` = `create_database(_settings().database_url)`,无注入口 → KB 读写落默认/管理库。
- `agent_app` boot `tenant_scope.open_kb_db(KB_MIGRATIONS)` 句柄**被丢弃**(对比 shared_memory/traces/reflection 都 `set_*_db` 注入了)。
- KB 检索用全局 `vector_store` + `knowledge_namespace(tenant,kb)`,不是 `KbScope.kb_vector_backend`(per-tenant `kb_vectors.db`)。
- `core/migrations.py` 仅核心 5 表;图谱(kb_entities/mentions/relations)+ connector_status 只在 alembic(管理库)。
- KB 写在 platform 侧(`kb_admin_api` / `admin_cli`),agent 侧只读(retrieval/graph_search)。

既有 spec(`tenant-scoped-db-routing`「agent 侧 store 连接来自路由、禁自连 Settings」)已要求这个,现实违反——X 落实它 + 补向量 + 补 platform 写上下文。

## Goals / Non-Goals

**Goals:**
- KB 关系(`kb_db`)+ 向量(`kb_vector_backend`)经 `tenant_scope` 注入,**agent 读 + platform 写两上下文都接**,去自连旁路。
- lift 图谱 3 + connector_status 进 KB_MIGRATIONS;砍 `kb_extraction_runs` + 死列;alembic drop 全部 KB 表。
- 多租户 KB 物理隔离(关系 + 向量)。

**Non-Goals:**
- KB 数据迁移(无存量真实数据 → 新建/重 ingest)。
- `agent_kbs` / `kb_connectors`(平台侧配置,留管理库)。
- KB 自进化 remediation(独立 change);KB 升格独立服务(远期)。

## Decisions

### D1：注入口 + 两上下文接线（照 memory/traces/shared_memory 模式）
`knowledge_base.runtime` 加 `set_database(db)` + 向量后端注入口(global，per-process 单租户)。
- **agent 读**:`agent_app` boot 接住 `kb_db = tenant_scope.open_kb_db(KB_MIGRATIONS)` + `tenant_scope.kb_vector_backend` → 注入。
- **platform 写**:`kb_admin_api` / `admin_cli` 的 ingest/sync/extraction 入口按 tenant 解析 `tenant_scope` → 注入(写本租户 kb.db / kb_vectors.db)。
**为何两头都接**:KB 写在 platform 侧、读在 agent 侧;只接 agent 读会让 platform ingest 仍写默认库,数据进不了 per-tenant kb.db。

### D2：去自连 + 去全局向量旁路
`runtime._database()`、`operations.py:default_database()`、`graph_search` 的 `Settings()` fallback 全删,改用注入句柄;`retrieval/search.py` 的 `vector_store.search(knowledge_namespace(...))` 改用注入的 `kb_vector_backend`。护栏测试断言无 `create_database(...settings...)` / 无全局 vector 旁路。

### D3：lift 图谱 3 + connector_status 进 KB_MIGRATIONS（保留 tenant_id/kb_id）
alembic 026(kb_entities/mentions/relations)+ 013(connector_status)的 DDL 原样 lift 进 `core/migrations.py`(append 现有核心 5 之后),保留 tenant_id/kb_id。**删 mentions/relations 的 `extraction_run_id` 列**(随 extraction_runs 砍)。

### D4：砍 kb_extraction_runs（审计→observability）
不进 kb.db。`extraction_store` 去掉 INSERT/UPDATE/get kb_extraction_runs;抽取仍产 entities/mentions/relations，run 摘要在内存构造同步返回(行为对调用方不变);若需运行审计,发 observability trace event,不养 KB 业务表。

### D5：alembic forward-drop 全部 KB 表（镜像 074）
新 alembic 迁移(接当前 head)drop `knowledge_bases`/`documents`/`chunks`/`chunks_fts`/`source_states`/`kb_entities`/`mentions`/`relations`/`connector_status`/`extraction_runs`，downgrade 重建。管理库不再含 KB 表;唯一真相源 = per-tenant kb.db（Y）。**无数据迁移**（无存量数据，被 drop 的多为空表）。

## Risks / Trade-offs

- [platform 写上下文按 tenant 注入遗漏 → ingest 仍写默认库] → ingest/sync/extraction 入口逐一过;集成测试断言 sync 后内容落 `<tenant>/kb.db` 而非默认库。
- [向量从"全局+namespace"切到 per-tenant backend，召回行为变化] → 行为应等价(同 tenant+kb 范围);加检索回归(ingest→search 命中)对照。
- [graph_search 跨 retrieval/runtime 取 db 的多处旁路漏改] → grep 全 KB 模块 `create_database`/`default_database`/`vector_store.search` + 护栏测试。
- [单进程注入 = 单租户/进程] → 与 agent 进程 per-agent(per-tenant)模型一致;platform ingest 每次按目标 tenant 注入(不跨租户复用句柄)。

## Migration Plan

1. KB_MIGRATIONS：lift 图谱3 + connector_status（删 extraction_run_id 列）;extraction_store 去 kb_extraction_runs。
2. runtime 加注入口 + 去自连;operations/graph_search/search 去旁路、用注入句柄 + kb_vector_backend。
3. agent_app boot 接 kb_db + kb_vector_backend;platform ingest 入口按 tenant 注入。
4. 新 alembic 迁移 forward-drop 全部 KB 表（接当前 head）。
5. 文档同步:data-model §3.5（KB 库表 + 物理位置 + 砍 extraction_runs）。
6. 回滚:纯路由 + schema 归属变更，无数据迁移;回滚还原注入与 KB_MIGRATIONS，alembic downgrade 重建 KB 表。

## Open Questions

- 无（关系+向量双接、两上下文、lift 范围、砍 extraction_runs、无数据迁移均已定）。
