## 0. 前置确认

- [ ] 0.1 确认本 change 实现普通 SQLite persistent backend，不引入 sqlite-vec native extension
- [ ] 0.2 确认不实现 Qdrant、OpenSearch / Elasticsearch adapter
- [ ] 0.3 确认不改变 `vector_store.upsert()` / `search()` / `delete()` public API
- [ ] 0.4 确认测试使用 tmp SQLite DB，不触碰 `data/`
- [ ] 0.5 确认基于已合并的 `embedding-rerank-provider-abstraction` runtime/provider 结构执行

## 1. 配置与 factory

- [ ] 1.1 Write failing tests: `VectorStoreSettings` 支持 `backend="sqlite"` 和可选 `database_url`
- [ ] 1.2 Write failing tests: 未配置 `vector_store.database_url` 时 sqlite backend 复用全局 `Settings.database_url`
- [ ] 1.3 Write failing tests: 非 sqlite database_url fail fast
- [ ] 1.4 实现 config / backend factory 调整：factory 接收已解析的 effective database_url，不在 backend 内部创建 `Settings`
- [ ] 1.5 运行 `uv run pytest tests/unit -x -q`，确认 1.1-1.3 红测转绿

## 2. SQLite backend schema

- [ ] 2.1 Write failing tests: sqlite backend 首次使用时创建 `vector_items` 表和 namespace 索引
- [ ] 2.2 Write failing tests: schema 包含 namespace、id、dimensions、vector_json、updated_at
- [ ] 2.3 使用 `aiosqlite` + direct SQL 实现 SQLite backend schema 初始化
- [ ] 2.4 运行 `uv run pytest tests/integration -x -q`，确认 2.1/2.2 红测转绿

## 3. Upsert / search / delete contract

- [ ] 3.1 Write failing tests: upsert 后重新创建 backend 仍可 search 到 id
- [ ] 3.2 Write failing tests: 同 namespace + id 重复 upsert 覆盖旧 vector，不产生重复记录
- [ ] 3.3 Write failing tests: search 只返回同 namespace 结果，不跨 namespace
- [ ] 3.4 Write failing tests: limit <= 0 返回空结果，limit > 0 限制返回数量
- [ ] 3.5 Write failing tests: delete 删除 namespace + id，其他 namespace 同 id 不受影响
- [ ] 3.6 实现 upsert / search / delete
- [ ] 3.7 运行 `uv run pytest tests/integration -x -q`，确认 3.1-3.5 红测转绿

## 4. Similarity / dimension / corrupt row handling

- [ ] 4.1 Write failing tests: search 结果按 score DESC、id ASC 稳定排序
- [ ] 4.2 Write failing tests: 维度不匹配记录被跳过，不影响其他结果
- [ ] 4.3 Write failing tests: vector_json 损坏记录被跳过，不影响其他结果
- [ ] 4.4 Write failing tests: 写入空 vector fail fast
- [ ] 4.5 实现 similarity 和异常记录处理
- [ ] 4.6 运行 `uv run pytest tests/integration -x -q`，确认 4.1-4.4 红测转绿

## 5. Runtime 接入与文档

- [ ] 5.1 Write failing tests: `vector_store.backend="sqlite"` 时 public `upsert/search/delete` 使用 SQLite backend
- [ ] 5.2 实现 runtime 接入
- [ ] 5.3 更新 `docs/capabilities/vector-store.md`：说明 SQLite persistent backend 已实现，sqlite-vec/Qdrant/OpenSearch 后置
- [ ] 5.4 运行 `uv run pytest tests/unit -x -q`
- [ ] 5.5 运行 `uv run pytest tests/integration -x -q`
- [ ] 5.6 运行 `uv run pytest -x -q`
- [ ] 5.7 运行 `uv run ruff format src tests`
- [ ] 5.8 运行 `uv run ruff check src tests`
- [ ] 5.9 运行 `uv run mypy src`
- [ ] 5.10 运行 `openspec validate vector-store-sqlite-backend`
