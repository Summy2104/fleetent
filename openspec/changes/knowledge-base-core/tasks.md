## 0. 前置确认

- [ ] 0.1 确认本 change 只实现最小 text / markdown ingest + vector-only search 闭环
- [ ] 0.2 确认不实现 parser、connector、BM25、hybrid、graph、sync、admin UI
- [ ] 0.3 确认新增表通过 Alembic migration 管理，不在应用代码中创建业务表
- [ ] 0.4 确认测试使用 tmp SQLite DB / monkeypatch，不触碰 `data/`

## 1. 配置与 public API

- [ ] 1.1 Write failing tests: `Settings.knowledge_base` 有 enabled/default tenant/default kb/chunk 参数默认值
- [ ] 1.2 Write failing tests: `KnowledgeDocument`、`KnowledgeChunk`、`ingest_text()`、`search()`、`delete()` 可导入
- [ ] 1.3 实现 config 和 package public API skeleton
- [ ] 1.4 运行 `uv run pytest tests/unit -x -q`

## 2. Schema 与 store

- [ ] 2.1 Write failing tests: Alembic fresh upgrade 创建 `knowledge_bases`、`knowledge_documents`、`knowledge_chunks`
- [ ] 2.2 Write failing tests: store 使用 named SQL parameters，不暴露 SQLite path / connection
- [ ] 2.3 实现 migration 和 store CRUD
- [ ] 2.4 运行 `uv run pytest tests/integration -x -q`

## 3. Ingest 与 chunking

- [ ] 3.1 Write failing tests: `ingest_text()` 保存 document 并生成 deterministic chunks
- [ ] 3.2 Write failing tests: chunking 保持顺序、空内容 fail fast、chunk_size/chunk_overlap 生效
- [ ] 3.3 Write failing tests: 每个 chunk 写入 `vector_store.upsert(chunk_id, chunk.content, kb namespace)`
- [ ] 3.4 实现 ingest/chunk/vector indexing
- [ ] 3.5 运行 `uv run pytest tests/integration -x -q`

## 4. Search 与 delete

- [ ] 4.1 Write failing tests: `search()` 调用 vector_store 按 `kb:{tenant_id}:{kb_id}` namespace 查询
- [ ] 4.2 Write failing tests: `search()` 支持多个 kb_ids，合并后按 score DESC、chunk position ASC 稳定排序
- [ ] 4.3 Write failing tests: tenant/kb 隔离，不跨 namespace 返回 chunk
- [ ] 4.4 Write failing tests: `delete(document_id)` 删除 document/chunks 并清理 vector entries
- [ ] 4.5 实现 search/delete
- [ ] 4.6 运行 `uv run pytest tests/integration -x -q`

## 5. long-term-ctx 接入与文档

- [ ] 5.1 Write failing tests: knowledge provider enabled 时 long-term-ctx 可注入 KB chunks
- [ ] 5.2 Write failing tests: KB disabled、未配置或无结果时 long-term-ctx 正常降级
- [ ] 5.3 实现 long-term-ctx provider adapter
- [ ] 5.4 更新 `docs/capabilities/knowledge-base.md`
- [ ] 5.5 运行 `uv run pytest -x -q`
- [ ] 5.6 运行 `uv run ruff format src tests`
- [ ] 5.7 运行 `uv run ruff check src tests`
- [ ] 5.8 运行 `uv run mypy src`
- [ ] 5.9 运行 `openspec validate knowledge-base-core`
