## 0. 前置确认

- [x] 0.1 确认 `knowledge-base-core` 已完成
- [x] 0.2 确认本 change 不引入 OpenSearch / Elasticsearch / LanceDB
- [x] 0.3 确认不接入 rerank、query planner 或 graph search

## 1. Search mode contract

- [x] 1.1 Write failing tests: `search()` 支持 vector / keyword / hybrid mode
- [x] 1.2 Write failing tests: unsupported search mode fail fast
- [x] 1.3 实现 search mode 参数和默认行为
- [x] 1.4 运行 `uv run pytest tests/unit -x -q`

## 2. FTS schema and indexing

- [x] 2.1 Write failing tests: Alembic upgrade 创建 knowledge-base-owned FTS 表或索引
- [x] 2.2 Write failing tests: ingest chunk 同步写入 keyword index
- [x] 2.3 Write failing tests: delete document 清理 keyword index
- [x] 2.4 实现 FTS schema 和 indexing
- [x] 2.5 运行 `uv run pytest tests/integration -x -q`

## 3. Keyword search

- [x] 3.1 Write failing tests: keyword mode 可命中精确产品编号 / 错误码
- [x] 3.2 Write failing tests: keyword search 按 tenant/kb 过滤
- [x] 3.3 Write failing tests: limit 和稳定排序生效
- [x] 3.4 实现 keyword retrieval
- [x] 3.5 运行 `uv run pytest tests/integration -x -q`

## 4. Hybrid RRF

- [x] 4.1 Write failing tests: hybrid 合并 vector 和 keyword candidates
- [x] 4.2 Write failing tests: 同一 chunk 同时被命中时去重并提升排序
- [x] 4.3 Write failing tests: vector 或 keyword 单侧为空时正常降级
- [x] 4.4 实现 RRF fusion
- [x] 4.5 运行 `uv run pytest tests/integration -x -q`

## 5. Docs and verification

- [x] 5.1 更新 `docs/capabilities/knowledge-base.md`
- [x] 5.2 运行 `uv run pytest -x -q`
- [x] 5.3 运行 `uv run ruff format src tests`
- [x] 5.4 运行 `uv run ruff check src tests`
- [x] 5.5 运行 `uv run mypy src`
- [x] 5.6 运行 `openspec validate knowledge-base-hybrid-search`
