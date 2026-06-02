## ADDED Requirements

### Requirement: Knowledge-base graph search public API
knowledge-base SHALL provide an independent graph search API that returns chunks with graph evidence without changing existing `search()` behavior.

#### Scenario: Graph search API is importable
- **WHEN** 调用方从 `fleetent.intelligence.knowledge_base` 导入 `graph_search`、`GraphSearchResult`、`GraphSearchChunk`、`EntityRef` 和 `RelationRef`
- **THEN** 导入成功

#### Scenario: Graph search is independent from search
- **WHEN** 调用 `graph_search(...)`
- **THEN** 系统不改变 `search(..., mode=\"vector\")`、`search(..., mode=\"keyword\")` 或 `search(..., mode=\"hybrid\")` 的行为

#### Scenario: Graph search returns wrapper results
- **WHEN** graph search 返回 chunks
- **THEN** 每个结果包含 `KnowledgeChunk`
- **AND** 包含 graph_score、reason、matched_entities、relations 和 evidence_chunk_ids

### Requirement: Deterministic graph entity matching
graph search SHALL match query text to entities using deterministic normalized string matching.

#### Scenario: Entity name match
- **WHEN** normalized query contains an entity normalized_name
- **THEN** graph search treats that entity as matched

#### Scenario: Entity alias match
- **WHEN** entity metadata contains aliases
- **AND** normalized query contains one alias
- **THEN** graph search treats that entity as matched

#### Scenario: No semantic entity search
- **WHEN** graph search matches entities
- **THEN** it does not call LLM, embedding search, rerank provider or vector store for entity linking

### Requirement: Graph search depth
graph search SHALL support depth 0 and depth 1 only.

#### Scenario: Depth zero returns direct entity mentions
- **WHEN** graph search runs with `depth=0`
- **THEN** it returns chunks containing direct mentions of matched entities
- **AND** result reason is `direct_entity_match`

#### Scenario: Depth one expands relations
- **WHEN** graph search runs with `depth=1`
- **THEN** it returns direct entity mention chunks
- **AND** relation evidence chunks
- **AND** related entity mention chunks allowed by relation direction

#### Scenario: Depth greater than one fails fast
- **WHEN** graph search runs with `depth > 1`
- **THEN** it fails fast

### Requirement: Direction-aware relation expansion
graph search SHALL expand relations according to relation type direction.

#### Scenario: Bidirectional relations expand both ways
- **WHEN** matched entity participates in `related_to` or `conflicts_with`
- **THEN** graph search can expand to the other entity from either side

#### Scenario: Directional relations expand source to target
- **WHEN** matched entity is the source of `depends_on`、`belongs_to`、`owns` or `defines`
- **THEN** graph search can expand to the target entity

#### Scenario: Directional relations do not reverse expand
- **WHEN** matched entity is the target of `depends_on`、`belongs_to`、`owns` or `defines`
- **THEN** graph search does not expand back to the source entity

#### Scenario: Mentions relation does not expand
- **WHEN** matched entity participates in `mentions`
- **THEN** graph search does not use that relation for related entity expansion

### Requirement: Graph search scoring and dedupe
graph search SHALL rank deterministic graph candidates by reason score and stable chunk ordering.

#### Scenario: Graph reason scores
- **WHEN** graph search scores candidates
- **THEN** direct entity match has score `1.0`
- **AND** relation evidence has score `0.8`
- **AND** related entity mention has score `0.6`

#### Scenario: Duplicate chunk merges evidence
- **WHEN** the same chunk is reached through multiple graph paths
- **THEN** graph search returns it once
- **AND** keeps the highest graph_score
- **AND** merges matched_entities、relations and evidence_chunk_ids

#### Scenario: Stable graph ordering
- **WHEN** graph search returns multiple chunks
- **THEN** results are ordered by graph_score DESC、chunk position ASC、chunk id ASC

#### Scenario: Limit is applied after merge
- **WHEN** graph search has more candidates than limit
- **THEN** final returned chunks do not exceed limit

### Requirement: Graph search scope isolation
graph search SHALL respect tenant and KB scope and exclude archived documents.

#### Scenario: Tenant and KB scoped reads
- **WHEN** graph search runs for tenant A and kb X
- **THEN** it only reads entities、mentions、relations and chunks from tenant A and kb X

#### Scenario: Multiple KBs are allowed
- **WHEN** graph search runs with multiple kb_ids
- **THEN** it can combine graph candidates from those KBs within the same tenant

#### Scenario: Archived documents are excluded
- **WHEN** graph evidence points to archived document chunks
- **THEN** graph search does not return those chunks

### Requirement: Graph search evaluation
knowledge-base SHALL include deterministic evaluation fixtures for graph search behavior.

#### Scenario: Direct entity evaluation
- **WHEN** evaluation query mentions a customer entity
- **THEN** expected customer chunks appear in graph search results
- **AND** forbidden other-customer chunks do not appear

#### Scenario: One-hop relation evaluation
- **WHEN** evaluation query matches an entity with a one-hop relation
- **THEN** direct mention、relation evidence and related entity mention chunks appear as expected

#### Scenario: Relation direction evaluation
- **WHEN** evaluation query matches the target of a directional relation
- **THEN** graph search does not return source chunks through reverse expansion
- **AND** bidirectional relations still expand both ways

### Requirement: Graph search exclusions
graph search SHALL NOT implement query planner, rerank integration, semantic entity search, LLM query understanding, document ACL or multi-hop graph traversal.

#### Scenario: Planner remains out of scope
- **WHEN** graph search change 完成
- **THEN** 系统不自动决定何时调用 graph search
- **AND** query planner 留给后续 spec

#### Scenario: Rerank remains out of scope
- **WHEN** graph search 返回 candidates
- **THEN** 它不调用 rerank provider

#### Scenario: Document ACL remains out of scope
- **WHEN** graph search 读取 graph evidence
- **THEN** 它只按 tenant + KB scope 过滤
- **AND** 不实现 document-level ACL
