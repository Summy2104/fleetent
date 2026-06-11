## 1. KB_MIGRATIONS 扩到全部 KB 关系表 + 砍 extraction_runs

- [x] 1.1 写测试（integration）：空 kb.db 经 `KB_MIGRATIONS` 迁移后含核心 5 + `kb_entities`/`kb_entity_mentions`/`kb_relations`/`knowledge_connector_status`，且不含 `kb_extraction_runs`、mentions/relations 无 `extraction_run_id` 列 —— 见红
- [x] 1.2 在 `knowledge_base/core/migrations.py` append 图谱 3 + connector_status 的 DDL（原样 lift alembic 026/013，保留 tenant_id/kb_id，删 extraction_run_id 列） —— 见绿
- [x] 1.3 `knowledge_base/extraction_store.py`：去掉 `kb_extraction_runs` 的 INSERT/UPDATE/get；抽取 run 摘要改内存构造同步返回（行为对调用方不变）；mentions/relations 写入不再带 extraction_run_id —— 见红→见绿

## 2. KB runtime 注入口 + 去自连/去全局向量旁路

- [x] 2.1 写测试（integration）：注入一个 kb_db 句柄后，`runtime._database()` 返回它而非 `create_database(Settings().database_url)`；无注入时不再 fallback 默认库（按基线行为） —— 见红
- [x] 2.2 `knowledge_base/runtime.py`：加 `set_database(db)` + 向量后端注入口（global，per-process）;`_database()` 用注入句柄 —— 见绿
- [x] 2.3 `operations.py`（去 `default_database()`）、`retrieval/graph_search.py`（去 `Settings()` fallback）、`retrieval/search.py`（向量改用注入的 `kb_vector_backend`，去 `vector_store.search(knowledge_namespace(...))` 全局旁路）—— 见红→见绿
- [x] 2.4 grep 自查 + 护栏测试：KB 模块无 `create_database(...settings...)` / 无全局 `vector_store.search(knowledge_namespace` 旁路

## 3. 两上下文接线（agent 读 + platform 写）

- [x] 3.1 写测试（integration）：agent boot 后，retrieval/graph_search 读本租户 `<tenant>/kb.db` + `<tenant>/kb_vectors.db`；多租户下 T1 进程够不到 T2 的 KB 库 —— 见红
- [x] 3.2 `runtime/agent_app.py`：接住 `kb_db = tenant_scope.open_kb_db(KB_MIGRATIONS)` + `tenant_scope.kb_vector_backend` → 注入 KB runtime（agent 读路径） —— 见绿
- [x] 3.3 写测试（integration）：platform ingest/sync/extraction 后，内容落本租户 `<tenant>/kb.db`（+ 向量落 `kb_vectors.db`），不落默认/管理库 —— 见红
- [x] 3.4 `platform/knowledge_base_management/kb_admin_api.py` + `platform/admin_cli/kb_connectors.py`：ingest/sync/extraction 入口按 tenant 解析 `tenant_scope` → 注入（platform 写路径） —— 见绿

## 4. alembic forward-drop 全部 KB 表

- [x] 4.1 写测试（integration）：全新管理库 `alembic upgrade head` 后不含任何 KB 表（核心/图谱/状态/extraction_runs 全无） —— 见红
- [x] 4.2 新增 alembic 迁移（接当前 head）：upgrade drop `knowledge_bases`/`knowledge_documents`/`knowledge_chunks`/`knowledge_chunks_fts`/`knowledge_source_states`/`kb_entities`/`kb_entity_mentions`/`kb_relations`/`knowledge_connector_status`/`kb_extraction_runs`；downgrade 重建 —— 见绿

## 5. 文档与收尾

- [x] 5.1 同步 `docs/architecture/data-model.md` §3.5：KB 库表（核心5+图谱3+connector_status，砍 extraction_runs）、关系 kb.db + 向量 kb_vectors.db 均 per-tenant；移除"图谱/connector 仍在管理库"的 ⚠️ 注记
- [x] 5.2 同步 `docs/capabilities/knowledge-base.md`：KB 数据 per-tenant（kb.db / kb_vectors.db）、ingest 写 / agent 读经路由注入、extraction 不再持久化 run-log
- [x] 5.3 验证基线：无 platform、管理库无 KB 表时，KB 读写落 per-tenant kb.db；`fleetent agent run` 检索正常
- [x] 5.4 change 收尾：`make test-pr` 全绿 + `uv run pytest tests/integration -q`（对照 main 基线，无新增失败）
