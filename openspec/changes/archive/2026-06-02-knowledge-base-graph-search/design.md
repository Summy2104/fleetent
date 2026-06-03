# Design

## 设计目标

第一版 graph search 的目标是“用已抽取的实体和关系找到相关 chunks，并解释为什么返回它们”。它不追求复杂图算法，也不改变现有 search 稳定性。

## Public API

建议 API：

```python
async def graph_search(
    query: str,
    tenant_id: str | None = None,
    kb_ids: list[str] | None = None,
    limit: int = 10,
    depth: int = 1,
) -> GraphSearchResult:
    ...
```

约束：

- `depth` 只支持 `0` 或 `1`。
- `limit <= 0` 返回空 chunks。
- tenant / kb 默认值对齐现有 knowledge-base settings。
- 不改变现有 `search()`。

## Return Shape

不复用裸 `KnowledgeChunk` 作为唯一返回值，而是使用 wrapper 保存 graph evidence。

```python
@dataclass(frozen=True)
class EntityRef:
    id: str
    entity_type: str
    name: str
    normalized_name: str

@dataclass(frozen=True)
class RelationRef:
    id: str
    relation_type: str
    source_entity_id: str
    target_entity_id: str
    evidence_chunk_id: str

@dataclass(frozen=True)
class GraphSearchChunk:
    chunk: KnowledgeChunk
    graph_score: float
    reason: Literal["direct_entity_match", "relation_evidence", "related_entity_mention"]
    matched_entities: list[EntityRef]
    relations: list[RelationRef]
    evidence_chunk_ids: list[str]

@dataclass(frozen=True)
class GraphSearchResult:
    query: str
    tenant_id: str
    kb_ids: list[str]
    depth: int
    chunks: list[GraphSearchChunk]
```

`KnowledgeChunk` 不增加 graph-specific 字段，避免污染现有 search contract。

## Entity Matching

第一版只做 deterministic string matching。

流程：

1. normalize query。
2. 读取 tenant + kb scope 内 entities。
3. 如果 `normalized_query contains entity.normalized_name`，视为 query matched entity。
4. 如果 entity metadata 包含 aliases，则 normalized alias 也参与匹配。

不做：

- entity embedding。
- semantic search。
- LLM entity linking。
- fuzzy matching。

## Search Flow

```text
query
  -> match entities deterministically
  -> fetch direct entity mention chunks
  -> if depth = 1:
       fetch relation evidence chunks
       expand related entities according to relation direction
       fetch related entity mention chunks
  -> merge by chunk id
  -> deterministic ranking
  -> return GraphSearchResult
```

### depth 0

只返回 direct entity mentions：

```text
matched entity -> entity mentions -> chunks
```

### depth 1

返回：

- direct entity mention chunks
- relation evidence chunks
- related entity mention chunks

## Relation Direction

双向展开：

```text
related_to
conflicts_with
```

单向展开：

```text
depends_on
belongs_to
owns
defines
```

不作为扩展关系：

```text
mentions
```

语义：

- 查询 source entity 时，单向 relation 可以展开到 target entity。
- 查询 target entity 时，单向 relation 不反向展开到 source entity。
- 双向 relation 两边都可展开。
- relation evidence chunk 可以作为 graph evidence 返回。

## Scoring and Ranking

固定分数：

```text
direct_entity_match = 1.0
relation_evidence = 0.8
related_entity_mention = 0.6
```

同 chunk 去重：

- 同一 chunk 只返回一次。
- 保留最高 graph_score。
- 合并 matched_entities、relations 和 evidence_chunk_ids。

排序：

```text
graph_score DESC
chunk.position ASC
chunk.id ASC
```

最终返回数量不超过 `limit`。

## Tenant / KB Scope

graph search 只读取请求 scope 内的数据：

- `tenant_id` 必须匹配。
- `kb_id` 必须在 `kb_ids` 内。
- archived documents 不返回。

不做 document-level ACL。Pilot / first version 仍使用 KB scope + agent binding 边界。

## Evaluation Fixtures

第一版 evaluation 至少覆盖三类：

1. 直接实体命中：
   - query：`Acme deployment`
   - entity：`customer: Acme`
   - expected：返回 Acme chunk
   - forbidden：不返回其他 customer chunk

2. 一跳关系展开：
   - relation：`Billing API depends_on Data Warehouse`
   - query：`Billing API dependency`
   - expected：返回 Billing API chunk、relation evidence chunk、Data Warehouse chunk

3. 方向性：
   - relation：`A depends_on B`
   - query：`B`
   - forbidden：不因 reverse depends_on 返回 A chunk
   - related_to / conflicts_with 应双向返回

fixture 可以手写 DB seed 或通过 deterministic extraction output 准备，不依赖真实 LLM。

## 与后续 specs 的关系

- `rerank-kb-search-integration` 可以在 graph candidates 生成后对 candidates 做 rerank，但本 change 不接 rerank。
- `knowledge-base-query-planner` 后续决定何时调用 vector / keyword / hybrid / graph / rerank。
- `reflection-knowledge-base-reports` 可复用 graph evidence 分析低命中或缺失关系。
