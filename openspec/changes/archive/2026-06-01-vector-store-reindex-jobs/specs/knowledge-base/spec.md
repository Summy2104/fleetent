## ADDED Requirements

### Requirement: Knowledge-base indexable iterator
knowledge-base SHALL 提供 public API，用于枚举指定 tenant/kb 当前应写入 vector_store 的 chunk source records。

#### Scenario: Knowledge-base indexable API is importable
- **WHEN** 调用方从 `fleetent.intelligence.knowledge_base` 导入 `iter_indexable_knowledge_chunks`
- **THEN** 导入成功

#### Scenario: Knowledge-base indexable items are tenant and kb scoped
- **WHEN** 多个 tenant 或 kb 都有 chunks
- **AND** 调用 `iter_indexable_knowledge_chunks(tenant_id, kb_id)`
- **THEN** 返回结果只包含该 tenant/kb 的 chunks

#### Scenario: Knowledge-base indexable item namespace
- **WHEN** `iter_indexable_knowledge_chunks()` 返回 item
- **THEN** item.namespace 等于 `knowledge_namespace(tenant_id, kb_id)`
- **AND** item.id 等于 chunk id
- **AND** item.content 等于 chunk content

### Requirement: Knowledge-base indexable iterator is a public boundary
vector_store reindex SHALL consume knowledge-base indexable records through knowledge-base public API, not direct SQL.

#### Scenario: Reindex does not query knowledge tables directly
- **WHEN** knowledge-base reindex 执行
- **THEN** reindex code 调用 `knowledge_base.iter_indexable_knowledge_chunks()`
- **AND** 不直接访问 `knowledge_documents`、`knowledge_chunks` 或 `knowledge_chunks_fts` 表
