## MODIFIED Requirements

### Requirement: Agent retrieval policy

Agent-side `knowledge.retrieval_policy` SHALL define how the Agent queries bound KBs. It MAY
include retrieval mode, top_k, rerank enablement, model route references for embedding/rerank,
and a planner opt-in (`use_planner`). When `use_planner` is true, the Agent passive retrieval path
SHALL route through `plan_knowledge_search` + `execute_knowledge_search_plan`(规则型:普通 query 走
hybrid、entity/relation-like query 先 graph、不足 hybrid fill),并把返回的 `KnowledgeChunk` 喂入既有
long-term-ctx 预算/选择管线。When `use_planner` is false(默认),retrieval path SHALL keep using
`search(mode=...)` with behavior unchanged.

#### Scenario: Hybrid retrieval policy
- **WHEN** `retrieval_policy.mode` is `hybrid` and `use_planner` is false
- **THEN** the Agent retrieval path uses hybrid KB search over the bound KBs

#### Scenario: Planner opt-in routes through planner
- **WHEN** `retrieval_policy.use_planner` is true
- **THEN** the Agent passive retrieval path calls `plan_knowledge_search` + `execute_knowledge_search_plan`
- **AND** relation-like queries may be escalated to graph evidence, with hybrid fill when insufficient
- **AND** the returned chunks feed the same long-term-ctx budget and selection pipeline

#### Scenario: Planner is off by default
- **WHEN** `retrieval_policy.use_planner` is not set
- **THEN** it defaults to false
- **AND** retrieval behavior is identical to the current `search(mode=...)` path

#### Scenario: Planner falls back safely without graph data
- **WHEN** `use_planner` is true but the bound KBs have no entity/relation graph data
- **THEN** the planner returns hybrid results and no error is raised

#### Scenario: Model routes are referenced by route key
- **WHEN** `retrieval_policy.embedding_route` or `retrieval_policy.rerank_route` is set
- **THEN** the value references a route key from the Agent model policy
- **AND** this spec treats the value as an opaque route-key string until Agent-scoped model routing
  wires model resolution
