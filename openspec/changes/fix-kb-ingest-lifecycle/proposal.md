## Why

代码审计发现 knowledge-base 模块存在两个单机环境下当前就会出错的数据正确性缺陷,与是否分机部署无关:

- **重复文档(D2)**:`ingest_text` / `ingest_parsed` 对同一篇文档重复导入时是纯 `INSERT`,产生重复的 `knowledge_documents` 与 `knowledge_chunks`,检索结果被同一内容多次污染,且无任何更新/去重路径。
- **幽灵实体(D1)**:hard `delete(document_id)` 只清理 documents/chunks/fts/向量,**不清理** `kb_entities` / `kb_entity_mentions` / `kb_relations`;被删文档的 mentions/relations 仍指向已不存在的 document_id,`graph_search` 读取层按 `archived_at` 的排除机制对硬删文档兜不住,会把"幽灵实体/关系"作为图证据返回。

两者都是正确性问题(不是性能或部署问题),应优先修复。

> **scope 收窄说明**:`archive`(软删、可恢复)的图证据已由现有 "Graph search scope isolation" 在**读取层**按 `archived_at` 排除,行为正确且需保留可恢复性,**本 change 不改 archive**。幽灵问题只发生在 hard `delete`。

## What Changes

- **manual ingest 增加文档身份与覆盖语义**:文档身份定义为 `(tenant_id, kb_id, source, filename)`。同身份再次 `ingest_text` / `ingest_parsed` 时,先删除旧 document 及其全部派生数据(chunks、chunks_fts、vector_store 向量、该文档的 mentions/relations),再写入新版本——"库里始终一份最新,无重复"。语义与 connector 的 `reingest_changed` 对齐。
- **hard delete 级联清理图数据**:`delete(document_id)` 删除该文档的 `kb_entity_mentions`(按 `document_id`)与 `kb_relations`(按 `evidence_document_id`),并垃圾回收"零剩余 mention 且不再被任何剩余 relation 引用"的 canonical `kb_entities`。
- **graph_search 不再命中已硬删文档的图证据**(由上面级联保证的可观察结果;archived 文档继续由现有读取层排除)。

不改变:`ingest_text` / `ingest_parsed` / `delete` / `archive` 的 public API 签名;**archive / archive_knowledge_base 行为**;connector 同步路径的现有身份(`source_path` / `content_hash`)与行为;extraction 显式触发(不自动抽取)的现有约束;`retrieval` 不得 import `ingest` 的护栏。

> **与现有 "Document-level replacement semantics" 的一致性**:该 requirement 规定 extraction 重跑后孤儿实体清理 deferred——那是"文档仍存在、瞬时孤儿很快重新挂上"的场景。本 change 的孤儿 GC 只在 hard delete(文档永久消失、真孤儿)时触发,触发点不同、不矛盾,该 requirement 不改。

## Capabilities

### New Capabilities
<!-- 无新增 capability -->

### Modified Capabilities
- `knowledge-base`: 新增 manual ingest 的文档身份与覆盖(re-ingest)行为要求;新增 delete / archive / archive_knowledge_base 对实体图数据的级联清理要求;明确 `graph_search` 不返回已删/已归档文档的图证据。

## Impact

- **owning package**:`fleetent.knowledge_base`(仅本模块)。
- **public API surface**:不变(仅改内部级联与去重行为)。
- **owned tables**:per-tenant `kb.db` 的 `knowledge_documents` / `knowledge_chunks` / `knowledge_chunks_fts` / `kb_entities` / `kb_entity_mentions` / `kb_relations`(均已存在)。若为 manual ingest 文档身份引入唯一约束,走 `knowledge_base/core/migrations.py` 的嵌入式 forward-only 迁移(新增有序 `(ver, sql)`),**不触碰 Alembic**。
- **vector_store**:覆盖与删除时调用既有 `vector_store.delete` / `upsert` public API,无新依赖。
- **config namespace**:无。
- **cross-module 依赖**:无新增;`platform` / `agent` / `node` 不受影响,无需改动。
- **测试**:integration 层(真实 SQLite + vector backend);覆盖 re-ingest 去重、共享实体不被误删、archive 后 graph_search 不命中。
