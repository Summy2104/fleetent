## 0. 前置确认

- [x] 0.1 确认本 change 不接 sqlite-vec、Qdrant、真实 embedding 模型或 HTTP embedding sidecar
- [x] 0.2 确认本 change 不修改 memory_layer、knowledge_base、long_term_ctx

## 1. 配置默认值

- [x] 1.1 Write failing tests: 默认配置包含 `vector_store.backend="memory"`、`embedding.backend="deterministic"`、`embedding.dimensions=64`
- [x] 1.2 在 config 中新增 vector_store / embedding 配置与默认值
- [x] 1.3 运行 `uv run pytest -x -q`，确认 1.1 红测转绿

## 2. Package 与 public API

- [x] 2.1 Write failing tests: 可从 `fleetent.intelligence.vector_store` 导入 `SearchResult`、`upsert`、`search`、`delete`、`memory_namespace`、`knowledge_namespace`
- [x] 2.2 新增 `fleetent.intelligence.vector_store` package 和 public API 骨架
- [x] 2.3 运行 `uv run pytest -x -q`，确认 2.1 红测转绿

## 3. Namespace helpers

- [x] 3.1 Write failing tests: `memory_namespace("u1") == "mem:u1"`；`knowledge_namespace("default", "global") == "kb:default:global"`；空值报错
- [x] 3.2 实现 namespace helper 与输入校验
- [x] 3.3 运行 `uv run pytest -x -q`，确认 3.1 红测转绿

## 4. Deterministic embedding

- [x] 4.1 Write failing tests: 同一文本 embedding 稳定、维度正确、非空文本向量归一化、空文本行为稳定
- [x] 4.2 实现 deterministic embedding backend
- [x] 4.3 运行 `uv run pytest -x -q`，确认 4.1 红测转绿

## 5. In-memory backend

- [x] 5.1 Write failing tests: upsert 后可 search；search 只返回 id 和 score；limit 生效
- [x] 5.2 实现 in-memory backend 的 upsert/search/delete
- [x] 5.3 运行 `uv run pytest -x -q`，确认 5.1 红测转绿

## 6. 隔离、覆盖和删除

- [x] 6.1 Write failing tests: namespace 隔离、同 id upsert 覆盖、delete 后不可检索
- [x] 6.2 补齐 backend 行为与稳定排序：score 降序，score 相同按 id 升序
- [x] 6.3 运行 `uv run pytest -x -q`，确认 6.1 红测转绿

## 7. Backend factory 与错误处理

- [x] 7.1 Write failing tests: unsupported vector backend / embedding backend 初始化失败且错误信息明确
- [x] 7.2 实现 backend factory，当前只接受 `memory` + `deterministic`
- [x] 7.3 运行 `uv run pytest -x -q`，确认 7.1 红测转绿

## 8. 收尾验证

- [x] 8.1 运行 `uv run pytest -x -q`
- [x] 8.2 运行 `uv run ruff format src tests`
- [x] 8.3 运行 `uv run ruff check src tests`
- [x] 8.4 运行 `uv run mypy src`
- [x] 8.5 运行 `openspec validate 2026-05-31-vector-store-foundation`
