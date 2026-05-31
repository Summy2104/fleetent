## Why

`knowledge-base` 目前只有迁移计划和能力域设计，没有运行时代码、表结构、ingest/search API。
5 月 31 日已经完成 database runtime、vector_store、SQLite vector backend、embedding provider 和
long-term-ctx 地基，下一步应先打通最小知识库闭环。

本 change 只做手动 text / markdown ingest → deterministic chunking → vector_store indexing →
`search()` 返回 `KnowledgeChunk` 的最小闭环，为 parser、connector、hybrid search、sync 和 graph
后续 specs 提供稳定 public API 与数据模型。

## What Changes

- 新增 `fleetent.intelligence.knowledge_base` package。
- 新增 `knowledge_base.*` 配置：
  - `default_tenant_id = "default"`
  - `default_kb_id = "global"`
  - `chunk_size`
  - `chunk_overlap`
  - `enabled`
- 新增 Alembic migration，创建 knowledge-base-owned tables：
  - `knowledge_bases`
  - `knowledge_documents`
  - `knowledge_chunks`
- 新增 public API：
  - `KnowledgeDocument`
  - `KnowledgeChunk`
  - `ingest_text(filename, content, tenant_id, kb_id, source, source_url)`
  - `search(query, tenant_id, kb_ids, limit)`
  - `delete(document_id)`
- `ingest_text()` 同步完成最小 ingest：保存 document、分块、保存 chunks、写入 vector_store。
- `search()` 先做 vector-only search：按 `kb:{tenant_id}:{kb_id}` namespace 查询 vector_store，回查
  `knowledge_chunks` 和 `knowledge_documents`，返回 `KnowledgeChunk`。
- `delete()` 删除 document/chunks，并删除对应 vector_store entries。
- long-term-ctx 可以通过 knowledge provider 调用 `knowledge_base.search()`；KB disabled 或无结果时不影响
  memory 注入。

## Out of Scope

- 不实现 parser framework；core 只接受 plain text / markdown content string。
- 不实现 local directory、Confluence、Google Drive connector。
- 不实现 BM25 / FTS5 / hybrid / rerank / query planner。
- 不实现 graph_search、entities、relations 或 `kb_extraction`。
- 不实现 sync planner、后台 job、admin UI、REST upload API。
- 不保存 raw query audit。

## Dependencies

- Requires existing database runtime and Alembic migration flow.
- Requires existing vector_store public API and SQLite backend.
- Requires existing long-term-ctx optional knowledge provider boundary.

## Execution Notes

This change is the serial root for the KB suite. `knowledge-base-parsers-basic`、
`knowledge-base-hybrid-search` and `knowledge-base-retrieval-evaluation` should not execute before
this one is merged into the suite branch.

## Impact

- **Code**: adds `intelligence.knowledge_base` runtime package and tests.
- **Database**: adds Alembic migration for KB-owned tables.
- **Docs**: updates `docs/capabilities/knowledge-base.md`.
- **Tests**: unit/integration tests use tmp SQLite DB and mocked/vector_store test doubles where needed.
