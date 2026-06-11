## MODIFIED Requirements

### Requirement: KB 为首个消费者

KB 关系库 SHALL 作为引擎的第一个消费者：把现 `knowledge_base/operations.py:ensure_schema()` 的 DDL 原样 lift 成 KB 的 `MIGRATIONS`（v1..vN），**保留 `tenant_id`/`kb_id` 列**，不借机改 schema。其余 agent 侧库（traces/memory/reflection 等）迁入 Y 不在本切片。

KB 的 `MIGRATIONS`（`core/migrations.py`）SHALL 覆盖**全部 KB 关系表**:核心 5（`knowledge_bases` / `knowledge_documents` / `knowledge_chunks` / `knowledge_chunks_fts` / `knowledge_source_states`）+ 知识图谱 3（`kb_entities` / `kb_entity_mentions` / `kb_relations`）+ `knowledge_connector_status`。图谱/状态表的 DDL 由 alembic（026/013）原样 lift（保留 `tenant_id`/`kb_id`）。`kb_extraction_runs` SHALL NOT 进 kb.db（砍除:只写审计、从不读回;抽取仍产 entities/mentions/relations，run 摘要同步返回，运行审计如需则发 observability trace event）;`kb_entity_mentions`/`kb_relations` 的 `extraction_run_id` 死列 SHALL 一并删除。管理库 alembic SHALL NOT 再定义任何 KB 表（上列各表的 alembic 孤立定义经 forward-drop 迁移移除，唯一真相源为 per-tenant `kb.db` 的 Y）。

#### Scenario: KB schema 经 Y 建出且与原 DDL 等价
- **WHEN** 一个空 KB 关系库经引擎迁移
- **THEN** 建出的表/列/索引等价于原 `ensure_schema()` 的产出（含 `tenant_id`/`kb_id` 列）

#### Scenario: 图谱 + connector_status 在 kb.db
- **WHEN** 一个空 KB 关系库经 `MIGRATIONS` 迁移
- **THEN** 库中含 `kb_entities` / `kb_entity_mentions` / `kb_relations` / `knowledge_connector_status`（不含 `kb_extraction_runs`，mentions/relations 无 `extraction_run_id` 列）

#### Scenario: 管理库不再定义 KB 表
- **WHEN** 全新管理库执行 `alembic upgrade head`
- **THEN** 库中不含任何 KB 表（核心/图谱/状态均已 forward-drop），KB 表只存在于 per-tenant `kb.db`
