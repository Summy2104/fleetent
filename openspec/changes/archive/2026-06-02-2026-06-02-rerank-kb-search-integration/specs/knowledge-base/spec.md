## MODIFIED Requirements

### Requirement: Hybrid RRF fusion
系统 SHALL 使用 RRF 或等价稳定策略融合 vector 和 keyword candidates。

#### Scenario: Hybrid deduplicates chunks
- **WHEN** 同一 chunk 同时出现在 vector 和 keyword candidates
- **THEN** hybrid result 只包含一次该 chunk

#### Scenario: Hybrid boosts dual matches
- **WHEN** 一个 chunk 同时被 vector 和 keyword 命中
- **THEN** 该 chunk 排名优先于只被单侧弱命中的候选

#### Scenario: Hybrid degrades when one side is empty
- **WHEN** vector 或 keyword 单侧无结果
- **THEN** hybrid search 仍返回另一侧结果

#### Scenario: Hybrid search does not rerank by default
- **WHEN** 调用 `search(..., mode="hybrid")` 且未传入 `rerank=True`
- **THEN** 系统不调用 rerank provider
- **AND** 返回当前 hybrid fused ranking

### Requirement: Hybrid search excludes advanced retrieval
knowledge-base search SHALL NOT implement rerank provider, query planner, graph search or external search
backend as part of default vector、keyword 或 hybrid search。

#### Scenario: Hybrid search does not rerank by default
- **WHEN** 调用 `search(..., mode="hybrid")` 且未传入 `rerank=True`
- **THEN** 系统不调用 rerank provider
- **AND** 返回当前 hybrid fused ranking

#### Scenario: Graph search remains separate
- **WHEN** 调用 `search(...)`
- **THEN** 系统不执行 graph search relation expansion

#### Scenario: Query planner remains separate
- **WHEN** 调用 `search(...)`
- **THEN** 系统不执行 planner-driven multi-step retrieval

## ADDED Requirements

### Requirement: Hybrid rerank opt-in
系统 SHALL 支持显式开启的 hybrid rerank，用 configured rerank provider 对 hybrid candidates 重排。

#### Scenario: Hybrid rerank is opt-in
- **WHEN** 调用 `search(query, mode="hybrid", rerank=True, limit=10)`
- **THEN** 系统先生成 hybrid candidates
- **AND** 调用 configured rerank provider 对 candidates 重排
- **AND** 返回数量不超过 10

#### Scenario: Existing search behavior remains default
- **WHEN** 调用 `search(query, mode="hybrid")`
- **THEN** 系统返回原 hybrid fused ranking
- **AND** 不调用 rerank provider

#### Scenario: Rerank only supports hybrid mode
- **WHEN** 调用 `search(query, mode="vector", rerank=True)` 或 `search(query, mode="keyword", rerank=True)`
- **THEN** 系统 fail fast
- **AND** 不调用 rerank provider

#### Scenario: Non-positive limit short-circuits
- **WHEN** 调用 `search(query, mode="hybrid", rerank=True, limit=0)`
- **THEN** 系统返回空列表
- **AND** 不调用 rerank provider

### Requirement: Hybrid rerank candidate pool
系统 SHALL 在 hybrid rerank 开启时扩大候选池，再返回 requested limit 内的结果。

#### Scenario: Candidate pool uses stable code constants
- **WHEN** `limit` 为 K 且 `rerank=True`
- **THEN** candidate pool size 等于 `min(max(K * 5, 20), 100)`
- **AND** 这些数值由 knowledge-base runtime 常量定义，不新增配置项

#### Scenario: Candidate pool feeds rerank provider
- **WHEN** hybrid rerank 执行
- **THEN** vector 和 keyword retrieval 使用 candidate pool size 生成 candidates
- **AND** rerank provider 接收按原 hybrid ranking 排序的 candidate content
- **AND** rerank provider 的 `top_n` 为 requested limit

### Requirement: Hybrid rerank result mapping
系统 SHALL 将 rerank provider 返回的 index + score 映射回 `KnowledgeChunk`，并保持结果稳定可解释。

#### Scenario: Provider order wins for valid indexes
- **WHEN** rerank provider 返回合法 indexes
- **THEN** 这些 chunks 按 provider 输出顺序排在前面
- **AND** 对应 `KnowledgeChunk.score` 使用 provider rerank score

#### Scenario: Illegal or duplicate provider indexes are ignored
- **WHEN** rerank provider 返回越界 index、负数 index 或重复 index
- **THEN** 系统忽略非法或重复项
- **AND** 继续处理其他有效结果

#### Scenario: Missing candidates are appended in hybrid order
- **WHEN** rerank provider 返回的有效结果少于 requested limit
- **THEN** 未被 provider 返回的 candidates 按原 hybrid order 追加
- **AND** 追加 chunks 保留原 hybrid score

### Requirement: Hybrid rerank failure fallback
系统 SHALL 在 rerank provider 不可用或失败时返回原 hybrid ranking，而不是让 search 失败。

#### Scenario: Disabled rerank provider falls back
- **WHEN** `rerank=True` 但 configured rerank provider disabled
- **THEN** 系统返回原 hybrid ranking
- **AND** 记录 structured warning

#### Scenario: Rerank provider error falls back
- **WHEN** rerank provider timeout、抛出 provider error 或返回无法使用的结果
- **THEN** 系统返回原 hybrid ranking
- **AND** 记录 structured warning

#### Scenario: Runtime event is emitted when available
- **WHEN** rerank fallback 发生且当前 runtime event boundary 可用
- **THEN** 系统 SHOULD 记录 `kb_rerank_failed` event
- **AND** 事件包含 tenant_id、kb_ids、limit、candidate_count 和 failure reason

### Requirement: Reranked knowledge-base retrieval evaluation
系统 SHALL 提供 deterministic evaluation coverage，用于验证 rerank 能改善 KB retrieval 排序。

#### Scenario: Deterministic rerank promotes expected chunk
- **WHEN** evaluation fixture 启用 deterministic rerank
- **THEN** expected chunk 出现在 top results 中
- **AND** 排名高于 rerank 前的干扰候选

#### Scenario: Forbidden chunks are not promoted
- **WHEN** evaluation fixture 包含 forbidden chunks
- **THEN** reranked results 的 top result 不包含 forbidden chunk

#### Scenario: Real rerank evaluation is opt-in
- **WHEN** 未显式开启 real rerank evaluation 环境变量
- **THEN** 不调用真实 rerank provider
