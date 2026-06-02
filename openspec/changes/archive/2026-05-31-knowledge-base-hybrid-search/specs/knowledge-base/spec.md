## ADDED Requirements

### Requirement: Knowledge-base search modes
系统 SHALL 支持 vector、keyword 和 hybrid 三种 knowledge-base search mode。

#### Scenario: Vector mode remains available
- **WHEN** 调用 `search(..., mode="vector")`
- **THEN** 系统使用 vector_store 检索 chunks

#### Scenario: Keyword mode is available
- **WHEN** 调用 `search(..., mode="keyword")`
- **THEN** 系统使用 SQLite FTS5 / BM25 检索 chunks

#### Scenario: Hybrid mode is available
- **WHEN** 调用 `search(..., mode="hybrid")`
- **THEN** 系统同时使用 vector 和 keyword candidates 并融合排序

#### Scenario: Unsupported search mode fails fast
- **WHEN** 调用方传入未知 mode
- **THEN** 系统 fail fast

### Requirement: Keyword indexing
系统 SHALL 为 knowledge chunks 维护 SQLite FTS5 keyword index。

#### Scenario: Ingest updates keyword index
- **WHEN** ingest 创建 chunk
- **THEN** chunk content 可被 keyword search 命中

#### Scenario: Delete removes keyword index entries
- **WHEN** document 被删除
- **THEN** 关联 chunks 不再被 keyword search 返回

#### Scenario: Keyword index is tenant and kb scoped
- **WHEN** 不同 tenant 或 kb 存在相同关键词
- **THEN** keyword search 只返回查询范围内的 chunks

### Requirement: Keyword retrieval behavior
系统 SHALL 支持适合企业文档的精确词检索。

#### Scenario: Exact identifiers are searchable
- **WHEN** chunk 包含产品编号、错误码或专有名词
- **THEN** keyword search 可以命中该 chunk

#### Scenario: Keyword search respects limit
- **WHEN** keyword search 找到多条结果
- **THEN** 返回数量不超过 limit

#### Scenario: Keyword search returns KnowledgeChunk
- **WHEN** keyword search 返回结果
- **THEN** result shape 仍为 `KnowledgeChunk`

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

### Requirement: Hybrid search excludes advanced retrieval
hybrid search SHALL NOT implement reranker, query planner, graph search or external search backend.

#### Scenario: No rerank dependency
- **WHEN** hybrid search 执行
- **THEN** 系统不调用 rerank provider
