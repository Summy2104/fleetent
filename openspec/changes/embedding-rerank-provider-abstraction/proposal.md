## Why

`vector_store` 当前只有 deterministic embedding backend，适合测试和本地开发，但不能代表真实语义检索质量。
后续 memory、knowledge-base、hybrid search 和 retrieval evaluation 都需要真实 embedding；knowledge-base
hybrid search 后续也可能需要 rerank。Embedding 和 rerank 都不是 chat/completion，接口形态与
现有 `model_router` 不同，但它们都需要 provider 化配置、HTTP 客户端、超时、认证和测试替身。

本 change 建立 embedding / rerank provider abstraction。fleetent 只实现客户端边界，不实现模型服务端。
默认保持 deterministic / disabled，不引入云托管服务作为默认路径。

## What Changes

- 定义 `EmbeddingProvider` abstraction：
  - `embed(text: str) -> list[float]`
  - 保留 deterministic embedding provider。
  - 新增 HTTP embedding provider，兼容 OpenAI-style `/v1/embeddings` 响应格式。
- 定义 `RerankProvider` abstraction：
  - `rerank(query: str, documents: list[str], top_n: int | None = None) -> list[RerankResult]`
  - 新增 `RerankResult(index, score)` 数据结构。
  - 默认 `disabled` rerank provider，调用时明确失败。
  - 新增 deterministic/test rerank provider，用于测试。
  - 新增 HTTP rerank provider，兼容常见 `{model, query, documents, top_n}` 请求格式。
- 扩展配置：
  - `embedding.backend` 继续默认为 `deterministic`。
  - 新增 `embedding.endpoint`、`embedding.model`、`embedding.api_key`、`embedding.timeout_seconds`。
  - 新增 `rerank.backend`，默认 `disabled`。
  - 新增 `rerank.endpoint`、`rerank.model`、`rerank.api_key`、`rerank.timeout_seconds`。
- `vector_store.upsert()` / `search()` public API 不变，继续通过 embedding provider 获取向量。
- 不把 rerank 接入 knowledge-base search；只提供 provider 边界，供后续 specs 使用。

## Provider API Shape

### HTTP embedding

请求兼容 OpenAI-style embeddings：

```json
{
  "model": "BAAI/bge-m3",
  "input": ["文本内容"]
}
```

响应：

```json
{
  "data": [
    {
      "embedding": [0.1, 0.2]
    }
  ]
}
```

### HTTP rerank

请求：

```json
{
  "model": "BAAI/bge-reranker-v2-m3",
  "query": "问题",
  "documents": ["doc1", "doc2"],
  "top_n": 2
}
```

响应第一版支持一种规范格式：

```json
{
  "results": [
    {"index": 0, "score": 0.91},
    {"index": 1, "score": 0.62}
  ]
}
```

后续如需兼容特定厂商差异，再增加 adapter，不在本 change 中扩展多种响应方言。

## Module Boundary Impact

- **owning package**：`intelligence.vector_store` owns embedding provider；rerank provider 暂放同一
  package 下作为 retrieval infrastructure，后续 knowledge-base 使用 public API。
- **public API surface**：
  - 新增 provider-level classes / factories：`EmbeddingProvider`、`RerankProvider`、`RerankResult`。
  - `vector_store.upsert()` / `search()` / `delete()` 不变。
- **owned tables**：无。
- **config namespace**：扩展 `embedding.*`，新增 `rerank.*`。
- **cross-module dependencies**：不依赖 knowledge-base；后续 knowledge-base 可依赖 rerank public API。
- **migration / shim plan**：无数据迁移；deterministic embedding 继续作为默认兼容路径。

## Impact

- **代码**：
  - 修改 config。
  - 扩展 vector_store embedding factory。
  - 新增 rerank provider module。
  - vector_store runtime 继续使用 embedding provider，不改上层调用。
- **测试**：
  - 覆盖 deterministic / HTTP embedding。
  - 覆盖 disabled / deterministic / HTTP rerank。
  - HTTP 测试使用 `respx` 或 mock transport，不调用真实外部服务。
- **数据**：无 schema 变更。
- **不包含**：
  - 不实现 embedding / rerank 服务端。
  - 不默认接 OpenAI 或第三方云服务。
  - 不把 rerank 接入 knowledge-base search。
  - 不做 hybrid search、sqlite-vec、Qdrant 或 retrieval evaluation。
  - 不重构 `model_router`。
