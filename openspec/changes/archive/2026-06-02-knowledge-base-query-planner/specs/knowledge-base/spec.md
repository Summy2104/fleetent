## ADDED Requirements

### Requirement: Knowledge search planner public API
系统 SHALL 提供独立的规则型 knowledge search planner，用于解释并执行 KB retrieval 策略。

#### Scenario: Planner API is importable
- **WHEN** 调用方从 `fleetent.intelligence.knowledge_base` 导入 `KnowledgeSearchOptions`、`KnowledgeSearchPlan`、`KnowledgeSearchStep`、`plan_knowledge_search` 和 `execute_knowledge_search_plan`
- **THEN** 导入成功

#### Scenario: Planner does not change existing search API
- **WHEN** 调用 `search(..., mode="vector")`、`search(..., mode="keyword")` 或 `search(..., mode="hybrid")`
- **THEN** 行为保持对应底层检索语义
- **AND** 系统不要求使用 planner

#### Scenario: Planner does not use LLM
- **WHEN** `plan_knowledge_search()` 执行
- **THEN** 系统不调用 LLM、model router 或 query rewrite provider

### Requirement: Rule-based knowledge search planning
planner SHALL 使用 deterministic rules 生成带 reason 的 retrieval steps。

#### Scenario: Default query uses hybrid
- **WHEN** query 没有实体或关系迹象
- **THEN** plan 包含 `hybrid_search` step
- **AND** reason 包含 `default_hybrid`

#### Scenario: Entity or relation query uses graph first
- **WHEN** query 包含实体或关系迹象
- **THEN** plan 包含 `graph_search` step
- **AND** reason 包含 `entity_like_query` 或 `relation_like_query`

#### Scenario: Graph plan includes hybrid fill
- **WHEN** plan 包含 `graph_search`
- **THEN** plan 也包含 `hybrid_fill`
- **AND** `hybrid_fill` 用于 graph 结果不足 requested limit 时补齐

#### Scenario: Rerank option affects hybrid only
- **WHEN** `KnowledgeSearchOptions.rerank=True`
- **THEN** plan 中 hybrid 相关 step 标记 rerank
- **AND** graph step 不标记 rerank

### Requirement: Knowledge search plan execution
系统 SHALL 能执行 planner 输出的 steps，并返回去重后的检索结果。

#### Scenario: Execute default hybrid plan
- **WHEN** 执行只包含 `hybrid_search` 的 plan
- **THEN** 系统调用 hybrid search
- **AND** 透传 query、tenant_id、kb_ids 和 limit

#### Scenario: Execute graph with hybrid fill
- **WHEN** 执行包含 `graph_search` 和 `hybrid_fill` 的 plan
- **THEN** 系统先执行 graph search
- **AND** graph 结果不足 limit 时执行 hybrid search 补齐

#### Scenario: Execution deduplicates chunks
- **WHEN** graph 和 hybrid 返回同一 chunk
- **THEN** 最终结果只包含一次该 chunk
- **AND** 保留 graph evidence 或 source reason

#### Scenario: Execution respects limit
- **WHEN** plan execution 返回结果
- **THEN** 数量不超过 plan limit

### Requirement: Planner observability
planner SHALL 输出可排查的 selected steps 和 reason 信号。

#### Scenario: Planner records decision reason
- **WHEN** `plan_knowledge_search()` 生成 plan
- **THEN** plan 中每个 step 包含 reason

#### Scenario: Executor records retrieval summary
- **WHEN** `execute_knowledge_search_plan()` 完成
- **THEN** 系统记录 selected steps、graph result count、hybrid fill count 和 rerank requested 状态的 structured event 或 log

### Requirement: Planner evaluation
系统 SHALL 提供 deterministic evaluation，验证 planner 对普通查询、关系查询和 rerank 查询的策略选择。

#### Scenario: Ordinary query fixture chooses hybrid
- **WHEN** evaluation 运行普通事实查询 fixture
- **THEN** planner 选择 hybrid search

#### Scenario: Relation query fixture chooses graph plus fill
- **WHEN** evaluation 运行关系型查询 fixture
- **THEN** planner 选择 graph search 和 hybrid fill

#### Scenario: Rerank fixture only reranks hybrid
- **WHEN** evaluation 运行 `rerank=True` fixture
- **THEN** hybrid step 使用 rerank
- **AND** graph step 不使用 rerank
