# knowledge-base-graph-search

## Why

`knowledge-base-entity-relation-extraction` 建立 entities / mentions / relations 后，knowledge-base 仍缺少一个只读检索入口来利用这些图数据。现有 `search()` 已支持 vector / keyword / hybrid，但不做关系展开，也不返回 graph evidence。

本 change 提供第一版独立 `graph_search`，用于验证关系型问题召回效果，并为后续 query planner、rerank integration 和 reflection KB reports 提供可解释 graph evidence。

## What Changes

- 新增独立 public API：`graph_search(query, tenant_id, kb_ids, limit, depth=1)`。
- 新增返回 wrapper：
  - `GraphSearchResult`
  - `GraphSearchChunk`
  - `EntityRef`
  - `RelationRef`
- graph search 只读 `kb_entities`、`kb_entity_mentions`、`kb_relations` 和 `knowledge_chunks`。
- query entity match 使用 deterministic normalized string matching；可读取 entity metadata aliases。
- 支持 depth `0` 和 `1`；`depth > 1` fail fast。
- relation expansion 方向感知：
  - 双向：`related_to`、`conflicts_with`
  - 单向：`depends_on`、`belongs_to`、`owns`、`defines`
  - 不展开：`mentions`
- deterministic scoring：
  - `direct_entity_match = 1.0`
  - `relation_evidence = 0.8`
  - `related_entity_mention = 0.6`
- 同 chunk 去重，保留最高 score 并合并 evidence。
- 新增 evaluation fixture 验证直接实体命中、一跳关系展开和方向性。

## 模块边界影响

- owning package：`intelligence.knowledge_base`。
- public API surface：
  - `graph_search`
  - `GraphSearchResult`
  - `GraphSearchChunk`
  - `EntityRef`
  - `RelationRef`
- owned tables：无新增；只读 entity extraction 已定义的 tables。
- config namespace：无新增。
- cross-module dependencies：
  - 依赖 knowledge-base entity extraction tables。
  - 不依赖 vector store、rerank provider、LLM 或 query planner。
- migration / shim plan：无 DB migration，无 shim。

## 非目标

- 不改变现有 `search()` / hybrid ranking。
- 不接 query planner。
- 不接 rerank provider。
- 不做 semantic entity search。
- 不做 LLM query understanding。
- 不做多跳 graph traversal。
- 不做 document-level ACL。
- 不做 graph database 或 ANN backend。
