## 0. 前置确认

- [ ] 0.1 确认 `vector-store-reindex-jobs` 已完成或已合入当前工作树
- [ ] 0.2 确认本 change 不新增 embedding provider、部署 runtime 或生产默认配置
- [ ] 0.3 确认默认 evaluation 使用 deterministic embedding，不调用真实外部服务
- [ ] 0.4 确认 evaluation 使用 tmp SQLite / tmp vector DB，不触碰 `data/`

## 1. Evaluation fixture schema

- [ ] 1.1 Write failing tests: fixture 必须包含 name、user_id、tenant_id、kb_id、memories、documents、queries
- [ ] 1.2 Write failing tests: query owner 只能是 `memory` 或 `knowledge_base`，top_k 必须为正整数
- [ ] 1.3 Implement: fixture loader / validator
- [ ] 1.4 Verify green: 运行 `uv run pytest tests/evaluation/test_memory_kb_embedding_eval.py -x -q`

## 2. Deterministic combined runner

- [ ] 2.1 Write failing tests: runner 使用 tmp fleetent DB 和 tmp vector DB
- [ ] 2.2 Write failing tests: runner 通过 memory source records 和 `vector_store.reindex(owner="memory")` 建立 memory index
- [ ] 2.3 Write failing tests: runner 通过 KB ingest 和 `vector_store.reindex(owner="knowledge_base")` 建立 KB index
- [ ] 2.4 Implement: deterministic combined embedding evaluation runner
- [ ] 2.5 Verify green: 运行 `uv run pytest tests/evaluation/test_memory_kb_embedding_eval.py -x -q`

## 3. Retrieval assertions

- [ ] 3.1 Write failing tests: memory query 命中 expected memory snippet
- [ ] 3.2 Write failing tests: memory query 不返回 forbidden memory snippet
- [ ] 3.3 Write failing tests: KB query 命中 expected KB chunk snippet
- [ ] 3.4 Write failing tests: KB query 不返回 forbidden KB chunk snippet
- [ ] 3.5 Implement: expected / forbidden assertion helpers and baseline fixtures
- [ ] 3.6 Verify green: 运行 `uv run pytest tests/evaluation/test_memory_kb_embedding_eval.py -x -q`

## 4. Optional real embedding guard

- [ ] 4.1 Write failing tests: 未设置 `FLEETENT_EVAL_REAL_EMBEDDING=1` 时 combined real embedding evaluation 被 skip
- [ ] 4.2 Write failing tests: 设置 opt-in 但缺少 endpoint、model、API key 或 dimensions 时 skip
- [ ] 4.3 Implement: opt-in real HTTP embedding runner guard
- [ ] 4.4 Verify green: 运行 `uv run pytest tests/evaluation/test_memory_kb_embedding_eval.py -x -q`

## 5. Docs and final verification

- [ ] 5.1 更新 `docs/capabilities/memory.md`
- [ ] 5.2 更新 `docs/capabilities/knowledge-base.md`
- [ ] 5.3 更新 `docs/capabilities/vector-store.md`
- [ ] 5.4 更新 `docs/capabilities/intelligence-roadmap.md`
- [ ] 5.5 更新 CI quality gate spec，说明 combined real embedding evaluation 不进入默认 PR gate
- [ ] 5.6 运行 `uv run pytest tests/evaluation/test_memory_kb_embedding_eval.py -x -q`
- [ ] 5.7 运行 `uv run ruff format src tests`
- [ ] 5.8 运行 `uv run ruff check src tests`
- [ ] 5.9 运行 `uv run mypy src`
- [ ] 5.10 运行 `uv run pytest -x -q`
- [ ] 5.11 运行 `openspec validate memory-and-kb-real-embedding-evaluation --strict`
- [ ] 5.12 运行 `git diff --check`
