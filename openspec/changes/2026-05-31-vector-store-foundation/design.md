## Overview

本 change 建立 vector_store 的最小可用基础设施。它不是生产级向量数据库实现，而是一个稳定、
可测试、可替换的抽象边界，让 memory、knowledge-base 和 long-term-ctx 后续可以围绕同一 API 开发。

## Package Boundary

新增 package：

```text
src/fleetent/intelligence/vector_store/
  __init__.py
  embeddings.py
  backend.py
  namespaces.py
```

`__init__.py` 只导出 public API。后续 sqlite-vec / Qdrant backend 可以继续放在该 package 内部。

## Public API

```python
@dataclass(frozen=True)
class SearchResult:
    id: str
    score: float


async def upsert(id: str, text: str, namespace: str) -> None:
    """Embed text and upsert vector by id in namespace."""


async def search(query: str, namespace: str, limit: int = 10) -> list[SearchResult]:
    """Return top-k ids by similarity within namespace."""


async def delete(id: str, namespace: str) -> None:
    """Delete one vector by id from namespace."""


def memory_namespace(user_id: str) -> str:
    """Return mem:{user_id}."""


def knowledge_namespace(tenant_id: str, kb_id: str) -> str:
    """Return kb:{tenant_id}:{kb_id}."""
```

API 只返回 id 和 score。业务数据由调用方按 id 回查自己 owned table。

## Configuration

新增配置：

```yaml
vector_store:
  backend: memory

embedding:
  backend: deterministic
  dimensions: 64
```

本 change 只支持：

- `vector_store.backend = "memory"`
- `embedding.backend = "deterministic"`

其他值 fail fast，并给出明确错误信息。

## Deterministic Embedding

deterministic embedding 用于测试和本地开发，不代表真实语义质量。

建议算法：

1. 将文本按 unicode 字符或简单 token 遍历。
2. 使用稳定 hash 将 token 映射到固定维度。
3. 累加权重后做 L2 normalize。

要求：

- 同一文本每次输出相同向量。
- 不依赖 Python 进程随机 hash seed。
- 空文本返回零向量或明确错误；本 change 建议返回零向量，便于调用方处理。
- 维度由配置决定，默认 64。

## In-Memory Backend

in-memory backend 存储结构按 namespace 隔离：

```python
dict[str, dict[str, list[float]]]
```

行为：

- upsert 同一 namespace + id 时覆盖旧向量。
- search 只在指定 namespace 内查找。
- delete 只删除指定 namespace + id。
- search 按 score 降序返回，score 相同时按 id 升序稳定排序。
- limit 小于等于 0 时返回空列表。

该 backend 不持久化，进程重启后数据丢失。

## Score Semantics

score 表示向量相似度，范围建议为 0 到 1。上层只依赖“越大越相关”，不得假设不同 backend
之间的 score 可直接比较。

## Error Handling

- unsupported vector backend：初始化失败，说明当前支持值。
- unsupported embedding backend：初始化失败，说明当前支持值。
- namespace 为空：API 抛 `ValueError`。
- id 为空：upsert/delete 抛 `ValueError`。
- search query 为空：允许执行，按 deterministic embedding 的零向量行为返回稳定结果。

## Testing

本 change 使用 TDD。重点测试：

- namespace helper 输出固定格式。
- deterministic embedding 稳定、维度正确、已归一化。
- upsert 后可 search。
- namespace 隔离。
- upsert 覆盖旧向量。
- delete 后不可检索。
- search 按 score 降序，score 相同按 id 稳定排序。
- unsupported backend 配置 fail fast。

## Future Work

后续独立 changes：

- `vector-store-sqlite-backend`
- `vector-store-qdrant-backend`
- `embedding-http-sidecar`
- `memory-sqlite-semantic-store`
- `knowledge-base-foundation`
