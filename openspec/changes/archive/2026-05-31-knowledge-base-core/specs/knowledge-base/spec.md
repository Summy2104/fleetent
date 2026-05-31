## ADDED Requirements

### Requirement: Knowledge-base runtime foundation
系统 SHALL 提供 `intelligence.knowledge_base` runtime package，用于手动导入文本内容、建立 chunk
索引并按 tenant + kb 隔离检索。

#### Scenario: Public API is importable
- **WHEN** 调用方导入 `KnowledgeDocument`、`KnowledgeChunk`、`ingest_text`、`search` 和 `delete`
- **THEN** 导入成功

#### Scenario: Knowledge-base config defaults
- **WHEN** 未显式配置 knowledge_base
- **THEN** `knowledge_base.enabled` 默认为 false
- **AND** `default_tenant_id` 默认为 `"default"`
- **AND** `default_kb_id` 默认为 `"global"`
- **AND** chunk size 和 overlap 有稳定默认值

#### Scenario: Knowledge-base owns schema
- **WHEN** Alembic upgrade 到 head
- **THEN** 数据库包含 knowledge-base-owned `knowledge_bases`、`knowledge_documents` 和 `knowledge_chunks`
- **AND** migration 标明 owner module 是 knowledge-base

### Requirement: Manual text ingest and chunk indexing
系统 SHALL 支持手动导入 text / markdown 内容，生成 deterministic chunks 并写入 vector_store。

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

### Requirement: Vector-only knowledge search
系统 SHALL 提供 vector-only `search(query, tenant_id, kb_ids, limit)`，返回相关 `KnowledgeChunk`。

#### Scenario: Search returns chunks with metadata
- **WHEN** query 命中已导入 chunks
- **THEN** 返回的 `KnowledgeChunk` 包含 chunk id、document id、filename、content、score、tenant_id 和 kb_id

#### Scenario: Search supports multiple knowledge bases
- **WHEN** `kb_ids` 包含多个 kb
- **THEN** 系统分别查询对应 namespace 并合并结果

#### Scenario: Search is tenant isolated
- **WHEN** tenant A 和 tenant B 有相似内容
- **THEN** tenant A 的 search 不返回 tenant B 的 chunks

#### Scenario: Search respects limit and stable ordering
- **WHEN** search 返回多条候选
- **THEN** 返回数量不超过 limit
- **AND** 结果按 score DESC、chunk position ASC、chunk id ASC 稳定排序

### Requirement: Knowledge document deletion
系统 SHALL 支持删除 document 及其 chunks 和 vector index entries。

#### Scenario: Delete removes document chunks
- **WHEN** 调用 `delete(document_id)`
- **THEN** document 和关联 chunks 不再被 search 返回

#### Scenario: Delete removes vector entries
- **WHEN** 删除 document
- **THEN** 系统为该 document 的每个 chunk 调用 `vector_store.delete(chunk_id, namespace)`

#### Scenario: Delete is idempotent
- **WHEN** 删除不存在或已删除的 document
- **THEN** 系统不报错

### Requirement: First implementation excludes advanced retrieval
第一版 knowledge-base runtime SHALL 明确排除 parser framework、connectors、hybrid search、graph search 和
sync planner。

#### Scenario: No connector dependency
- **WHEN** core change 完成
- **THEN** runtime 不依赖 Confluence、Google Drive、本地目录扫描或外部 connector SDK

#### Scenario: No hybrid or graph search
- **WHEN** core change 完成
- **THEN** runtime 不创建 FTS/BM25、entities 或 relations 表
