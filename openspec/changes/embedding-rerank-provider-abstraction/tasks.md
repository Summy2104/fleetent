## 0. 前置确认

- [ ] 0.1 确认本 change 只做 embedding / rerank provider abstraction，不实现模型服务端
- [ ] 0.2 确认不把 rerank 接入 knowledge-base search，不做 retrieval evaluation
- [ ] 0.3 确认默认配置不调用真实外部服务

## 1. 配置扩展

- [ ] 1.1 Write failing tests: `EmbeddingSettings` 包含 backend、dimensions、endpoint、model、api_key_env、timeout_seconds 默认值
- [ ] 1.2 Write failing tests: `Settings` 包含 `rerank` 配置，默认 `backend="disabled"`
- [ ] 1.3 Write failing tests: `RerankSettings` 包含 backend、endpoint、model、api_key_env、timeout_seconds 默认值
- [ ] 1.4 实现配置字段
- [ ] 1.5 运行 `uv run pytest tests/unit -x -q`，确认 1.1-1.3 红测转绿

## 2. Embedding provider abstraction

- [ ] 2.1 Write failing tests: deterministic embedding provider 仍为默认且行为不变
- [ ] 2.2 Write failing tests: `embedding.backend="http"` 创建 HTTP embedding provider
- [ ] 2.3 Write failing tests: HTTP embedding provider 发送 OpenAI-style payload，并在 `api_key_env` 有值且环境变量存在时发送 Authorization header
- [ ] 2.4 Write failing tests: 空文本不发 HTTP 请求并返回零向量
- [ ] 2.5 Write failing tests: 非 2xx、timeout、malformed JSON、维度不匹配时报明确错误
- [ ] 2.6 Write failing tests: HTTP provider 失败时不静默 fallback 到 deterministic
- [ ] 2.7 实现 async `EmbeddingProvider` abstraction 和 HTTP provider
- [ ] 2.8 运行 `uv run pytest tests/integration -x -q`，确认 2.1-2.6 红测转绿

## 3. Rerank provider abstraction

- [ ] 3.1 Write failing tests: `RerankResult(index, score)` 可导入且只暴露 index / score
- [ ] 3.2 Write failing tests: disabled rerank provider 调用时明确失败
- [ ] 3.3 Write failing tests: deterministic rerank provider 用于测试，返回稳定排序
- [ ] 3.4 Write failing tests: HTTP rerank provider 发送 `{model, query, documents, top_n}` payload，并在 `api_key_env` 有值且环境变量存在时发送 Authorization header
- [ ] 3.5 Write failing tests: HTTP rerank provider 解析 `results[{index, score}]`
- [ ] 3.6 Write failing tests: 非 2xx、timeout、malformed JSON、越界 index、非数字 score 报明确错误
- [ ] 3.7 Write failing tests: HTTP provider 失败时不静默 fallback 到 deterministic rerank
- [ ] 3.8 实现 async rerank provider module 和 factory
- [ ] 3.9 运行 `uv run pytest tests/integration -x -q`，确认 3.1-3.7 红测转绿

## 4. Vector store runtime 接入

- [ ] 4.1 Write failing tests: `vector_store.upsert()` 使用配置的 HTTP embedding provider
- [ ] 4.2 Write failing tests: `vector_store.search()` 使用配置的 HTTP embedding provider
- [ ] 4.3 确认 `upsert/search/delete` public API 不变
- [ ] 4.4 实现 runtime 接入或 factory 调整
- [ ] 4.5 运行 `uv run pytest tests/integration -x -q`，确认 4.1/4.2 红测转绿

## 5. 文档与收尾验证

- [ ] 5.1 更新 `docs/capabilities/vector-store.md`：说明 embedding / rerank provider abstraction 已定义，rerank 尚未接入 KB search
- [ ] 5.2 运行 `uv run pytest tests/unit -x -q`
- [ ] 5.3 运行 `uv run pytest tests/integration -x -q`
- [ ] 5.4 运行 `uv run pytest -x -q`
- [ ] 5.5 运行 `uv run ruff format src tests`
- [ ] 5.6 运行 `uv run ruff check src tests`
- [ ] 5.7 运行 `uv run mypy src`
- [ ] 5.8 运行 `openspec validate embedding-rerank-provider-abstraction`
