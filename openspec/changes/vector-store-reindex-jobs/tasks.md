## 0. 前置确认

- [ ] 0.1 确认本 change 只做同步 reindex public API，不做后台任务平台
- [ ] 0.2 确认不新增 `reindex_jobs` / `reindex_items` 持久表
- [ ] 0.3 确认 reindex 不直接 SQL 访问 memory 或 knowledge-base owned tables
- [ ] 0.4 确认 `rebuild` 会先清空目标 namespace，再按 source of truth 全量 upsert

## 1. Vector namespace clearing

- [ ] 1.1 Write failing tests: `clear_namespace()` 可从 `fleetent.intelligence.vector_store` 导入
- [ ] 1.2 Write failing tests: in-memory backend 清空指定 namespace 后 search 不再返回旧 vectors，其他 namespace 不受影响
- [ ] 1.3 Write failing tests: SQLite backend 清空指定 namespace 后 search 不再返回旧 vectors，其他 namespace 不受影响
- [ ] 1.4 Implement: backend protocol、in-memory backend、SQLite backend 和 runtime public API 支持 `clear_namespace()`
- [ ] 1.5 Verify green: 运行 `uv run pytest tests/unit/test_vector_store.py tests/integration/test_vector_store_sqlite.py -x -q`

## 2. Indexable source iterators

- [ ] 2.1 Write failing tests: `IndexableItem` 可从 `fleetent.intelligence.vector_store` 导入
- [ ] 2.2 Write failing tests: `memory_layer.iter_indexable_memories(user_id)` 返回未过期 memory items，namespace 为 `mem:{user_id}`
- [ ] 2.3 Write failing tests: `iter_indexable_memories()` 不返回其他 user 的 memory，也不返回已过期 context memory
- [ ] 2.4 Write failing tests: `knowledge_base.iter_indexable_knowledge_chunks(tenant_id, kb_id)` 返回 chunks，namespace 为 `kb:{tenant_id}:{kb_id}`
- [ ] 2.5 Write failing tests: `iter_indexable_knowledge_chunks()` 不返回其他 tenant/kb 的 chunks
- [ ] 2.6 Implement: memory 和 knowledge-base indexable iterator public APIs
- [ ] 2.7 Verify green: 运行 `uv run pytest tests/unit/test_memory_indexable_items.py tests/unit/test_knowledge_base_indexable_items.py -x -q`

## 3. Reindex public API shape

- [ ] 3.1 Write failing tests: `ReindexRequest`、`ReindexSummary` 和 `reindex()` 可从 `fleetent.intelligence.vector_store` 导入，summary 包含 owner、namespace、dry_run、scanned、reindexed、skipped、failed
- [ ] 3.2 Write failing tests: 不支持的 owner、缺失 user_id、缺失 kb_id、未知 mode 均 fail fast
- [ ] 3.3 Write failing tests: dry-run 返回 namespace 和 scanned 计数，但不调用 `clear_namespace()` 或 `upsert()`
- [ ] 3.4 Implement: reindex dataclasses、request validation 和 dry-run path
- [ ] 3.5 Verify green: 运行 `uv run pytest tests/unit/test_vector_store_reindex.py -x -q`

## 4. Memory reindex execution

- [ ] 4.1 Write failing tests: memory rebuild 调用 `clear_namespace(mem:{user_id})`
- [ ] 4.2 Write failing tests: memory rebuild 对 iterator 返回的每个 item 调用 `upsert(id, content, namespace)`
- [ ] 4.3 Write failing tests: 单个 memory item upsert 失败计入 failed，后续 item 继续执行
- [ ] 4.4 Implement: memory owner rebuild execution
- [ ] 4.5 Verify green: 运行 `uv run pytest tests/unit/test_vector_store_reindex.py -x -q`

## 5. Knowledge-base reindex execution

- [ ] 5.1 Write failing tests: knowledge-base rebuild 调用 `clear_namespace(kb:{tenant_id}:{kb_id})`
- [ ] 5.2 Write failing tests: knowledge-base rebuild 对 iterator 返回的每个 chunk 调用 `upsert(id, content, namespace)`
- [ ] 5.3 Write failing tests: 单个 chunk upsert 失败计入 failed，后续 chunk 继续执行
- [ ] 5.4 Implement: knowledge-base owner rebuild execution
- [ ] 5.5 Verify green: 运行 `uv run pytest tests/unit/test_vector_store_reindex.py -x -q`

## 6. Integration behavior

- [ ] 6.1 Write failing tests: memory rebuild 清理 stale vector 后只保留当前 memory items 可检索
- [ ] 6.2 Write failing tests: knowledge-base rebuild 清理 stale vector 后只保留当前 chunks 可检索
- [ ] 6.3 Implement: integration fixes discovered by end-to-end reindex tests
- [ ] 6.4 Verify green: 运行 `uv run pytest tests/integration/test_vector_store_reindex.py -x -q`

## 7. Docs and final verification

- [ ] 7.1 更新 `docs/capabilities/vector-store.md`
- [ ] 7.2 更新 `docs/capabilities/memory.md`
- [ ] 7.3 更新 `docs/capabilities/knowledge-base.md`
- [ ] 7.4 更新 `docs/capabilities/intelligence-roadmap.md`
- [ ] 7.5 运行 `uv run ruff format src tests`
- [ ] 7.6 运行 `uv run ruff check src tests`
- [ ] 7.7 运行 `uv run mypy src`
- [ ] 7.8 运行 `uv run pytest -x -q`
- [ ] 7.9 运行 `openspec validate vector-store-reindex-jobs --strict`
- [ ] 7.10 运行 `git diff --check`
