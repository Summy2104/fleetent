## ADDED Requirements

### Requirement: Deterministic budget policy
系统 SHALL 提供确定性的 long-term context budget policy，用于在 memory 和 knowledge 候选内容之间分配长期上下文预算。

#### Scenario: Effective budget uses runtime and config caps
- **WHEN** agent-runtime 调用 `build_context(..., available_tokens=N)`
- **THEN** long-term-ctx 使用 `available_tokens` 与 `long_term_ctx.max_tokens` 的较小值作为 effective budget
- **AND** 注入文本不超过 effective budget

#### Scenario: Zero budget records budget decision
- **WHEN** `available_tokens <= 0`
- **THEN** `build_context()` 返回空 `text` 和空 `sources`
- **AND** 系统不调用 memory provider 或 knowledge provider
- **AND** budget metadata 记录 `zero_available_tokens`

### Requirement: Source budget limits
系统 SHALL 分别限制 memory 和 knowledge 的 token budget 与 top-k。

#### Scenario: Memory budget limits memory injection
- **WHEN** memory 候选内容超过 `long_term_ctx.memory_max_tokens`
- **THEN** 系统只注入 memory budget 内的候选内容
- **AND** 被排除的 memory 候选在 budget metadata 中记录 `source_budget_exceeded`

#### Scenario: Knowledge budget limits knowledge injection
- **WHEN** knowledge 候选内容超过 `long_term_ctx.knowledge_max_tokens`
- **THEN** 系统只注入 knowledge budget 内的候选内容
- **AND** 被排除的 knowledge 候选在 budget metadata 中记录 `source_budget_exceeded`

#### Scenario: Source top-k limits injected count
- **WHEN** memory 或 knowledge 候选数量超过对应 top-k
- **THEN** 系统只注入对应 top-k 内的候选内容
- **AND** 被排除候选在 budget metadata 中记录 `source_top_k_exceeded`

### Requirement: Source-aware conflict preference
系统 SHALL 在 memory 和 knowledge 候选内容冲突时使用保守的来源偏好。

#### Scenario: Factual query prefers knowledge
- **WHEN** query 是事实、流程、制度、项目资料或企业参考类问题
- **AND** memory 与 knowledge 候选内容存在来源冲突
- **THEN** budget policy 优先注入 knowledge 候选

#### Scenario: Personal history query prefers memory
- **WHEN** query 是用户偏好、用户历史、历史承诺或个人 / 团队背景类问题
- **AND** memory 与 knowledge 候选内容存在来源冲突
- **THEN** budget policy 优先注入 memory 候选

#### Scenario: Explicit conflict preference overrides auto
- **WHEN** `long_term_ctx.conflict_preference` 设置为 `memory` 或 `knowledge`
- **THEN** budget policy 使用配置的来源偏好
- **AND** 不使用 auto query intent 判断覆盖该配置

### Requirement: Budget decision metadata
`BuiltContext` SHALL 返回预算决策元数据，用于解释哪些来源被注入或排除。

#### Scenario: Included sources are recorded
- **WHEN** memory 或 knowledge 候选被注入
- **THEN** budget metadata 记录该来源的 source id、source type、token estimate 和 include reason
- **AND** `BuiltContext.sources` 包含该来源摘要

#### Scenario: Excluded sources are recorded
- **WHEN** 候选内容因低相关度、source top-k、source budget 或 total budget 被排除
- **THEN** budget metadata 记录该来源的 source id、source type、token estimate 和 exclusion reason
- **AND** `BuiltContext.sources` 不包含该来源摘要

#### Scenario: Sources only include injected content
- **WHEN** 某条候选内容未被注入
- **THEN** `BuiltContext.sources` 不包含该候选内容

### Requirement: Conservative policy scope
long-term context budget policy SHALL NOT 使用 LLM 做上下文选择、总结、改写或压缩。

#### Scenario: Policy is deterministic
- **WHEN** 相同 query、相同候选内容、相同配置和相同 available_tokens 被传入
- **THEN** budget policy 产生相同的注入结果和 budget metadata
- **AND** 不调用 LLM、embedding provider、rerank provider 或外部 HTTP 服务来决定预算
