## MODIFIED Requirements

### Requirement: Manual text ingest and chunk indexing
系统 SHALL 支持手动导入 text / markdown 内容，生成 deterministic chunks 并写入 vector_store。manual ingest 的文档身份 SHALL 为 `(tenant_id, kb_id, source, filename)`；对同一身份重复导入时，系统 SHALL 以覆盖（overwrite）语义替换旧文档，使该身份在库中始终只保留最新一份，不产生重复 document 或 chunk。

#### Scenario: Ingest creates document and chunks
- **WHEN** 调用 `ingest_text(filename, content, tenant_id, kb_id, source, source_url)`
- **THEN** 系统创建 document record
- **AND** 系统按 deterministic chunking 创建有序 chunks

#### Scenario: Empty content is rejected
- **WHEN** 导入内容为空或全空白
- **THEN** 系统 fail fast

#### Scenario: Chunks are indexed in vector store
- **WHEN** ingest 创建 chunk
- **THEN** 系统调用 `vector_store.upsert(chunk_id, chunk_content, knowledge_namespace(tenant_id, kb_id))`

#### Scenario: Ingest is tenant and kb scoped
- **WHEN** 同一 filename 被导入不同 tenant 或 kb
- **THEN** records 与 vector namespace 相互隔离

#### Scenario: Re-ingest same identity overwrites previous document
- **WHEN** 以相同 `(tenant_id, kb_id, source, filename)` 再次调用 `ingest_text` 或 `ingest_parsed`
- **THEN** 系统先删除旧 document 及其全部派生数据（chunks、chunks_fts、对应 `vector_store` 向量、该文档的 `kb_entity_mentions` 与 `kb_relations`，并 GC 由此产生的孤儿 `kb_entities`）
- **AND** 系统写入新版本的 document 与 chunks
- **AND** search 与 graph_search 只返回新版本内容，不返回旧版本残留

#### Scenario: Re-ingest does not duplicate
- **WHEN** 同一身份连续导入两次内容
- **THEN** 该身份在库中只存在一份 document
- **AND** 该 document 的 chunk 数量与单次导入一致，无重复 chunk

#### Scenario: Differing identity does not overwrite
- **WHEN** filename 相同但 `source` 不同（或 tenant/kb 不同）
- **THEN** 视为不同文档，各自独立保留，互不覆盖

### Requirement: Knowledge document deletion
系统 SHALL 支持删除 document 及其 chunks 和 vector index entries，并 SHALL 级联清理该文档贡献的实体图证据。hard delete 后，系统 SHALL 删除该文档的 `kb_entity_mentions`（按 `document_id`）与 `kb_relations`（按 `evidence_document_id`），并垃圾回收满足“零剩余 mention 且不再被任何剩余 relation 作为 source 或 target 引用”的 canonical `kb_entities`；被其它文档仍在引用的共享 entity SHALL 保留。

#### Scenario: Delete removes document chunks
- **WHEN** 调用 `delete(document_id)`
- **THEN** document 和关联 chunks 不再被 search 返回

#### Scenario: Delete removes vector entries
- **WHEN** 删除 document
- **THEN** 系统为该 document 的每个 chunk 调用 `vector_store.delete(chunk_id, namespace)`

#### Scenario: Delete removes the document's mentions and relations
- **WHEN** 删除一个已抽取过实体的 document
- **THEN** 系统删除该 document 的 `kb_entity_mentions` 与 `kb_relations`
- **AND** graph_search 不再返回指向已删 document 的图证据

#### Scenario: Orphan entities are garbage collected on delete
- **WHEN** 删除文档后某 canonical entity 不再有任何 mention，且不再被任何剩余 relation 引用
- **THEN** 系统删除该孤儿 `kb_entities` 行

#### Scenario: Shared entities survive deletion
- **WHEN** 删除文档后某 entity 仍被另一个未删文档的 mention 或 relation 引用
- **THEN** 系统保留该 entity，不删除

#### Scenario: Delete is idempotent
- **WHEN** 删除不存在或已删除的 document
- **THEN** 系统不报错
