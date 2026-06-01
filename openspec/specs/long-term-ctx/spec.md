# long-term-ctx Specification

## Purpose
Coordinate long-term context retrieval and prompt injection across semantic memory and
optional knowledge providers without owning storage or knowledge-base runtime behavior.
## Requirements
### Requirement: Long-term context public API
系统 SHALL 提供 `BuiltContext`、`ContextSource` 和
`build_context(user_id, query, agent_id, available_tokens)` public API，用于构建可注入
agent prompt 的长期上下文。

#### Scenario: Public API is importable
- **WHEN** 调用方从 long-term-ctx 模块导入 `BuiltContext`、`ContextSource` 和 `build_context`
- **THEN** 导入成功

#### Scenario: Built context contains text and sources
- **WHEN** `build_context()` 返回结果
- **THEN** 结果包含 `text` 和 `sources` 字段

### Requirement: Empty token budget short-circuit
系统 SHALL 在可用 token 预算为零或负数时跳过长期上下文检索。

#### Scenario: Zero token budget returns empty context
- **WHEN** 调用 `build_context(..., available_tokens=0)`
- **THEN** 返回空 `text` 和空 `sources`
- **AND** 系统不调用 memory provider 或 knowledge provider

### Requirement: Memory context retrieval
`build_context()` SHALL 调用 memory-layer semantic search 并将结果格式化为 memory 区段。

#### Scenario: Memory results are included
- **WHEN** memory-layer 返回相关 memory items
- **THEN** `BuiltContext.text` 包含 memory 区段
- **AND** `BuiltContext.sources` 包含 `source_type="memory"` 的来源摘要

#### Scenario: Empty memory results are omitted
- **WHEN** memory-layer 返回空结果
- **THEN** `BuiltContext.text` 不包含空的 memory 区段

### Requirement: Optional knowledge provider
系统 SHALL 将 knowledge-base 作为可选 provider；knowledge-base 未启用、未配置或返回空结果时，
long-term-ctx 仍正常返回可用上下文。

#### Scenario: Knowledge provider disabled
- **WHEN** knowledge provider 未配置或被禁用
- **THEN** `build_context()` 不抛出异常
- **AND** 如果 memory 有结果，则正常返回 memory context

#### Scenario: Knowledge provider returns empty results
- **WHEN** knowledge provider 返回空结果
- **THEN** `BuiltContext.text` 不包含空的 knowledge 区段

#### Scenario: Knowledge results are included when available
- **WHEN** knowledge provider 返回相关 chunks
- **THEN** `BuiltContext.text` 包含 knowledge 区段
- **AND** `BuiltContext.sources` 包含 `source_type="knowledge"` 的来源摘要

#### Scenario: Built-in provider uses knowledge-base search
- **WHEN** `knowledge_base.enabled=true`
- **THEN** long-term-ctx 可以通过 built-in provider 调用 `knowledge_base.search()`
- **AND** provider 返回的 source id 对应 chunk id

### Requirement: Context merge and budget control
系统 SHALL 合并 memory 与 knowledge 结果，并保证注入文本不超过可用 token 预算与配置上限中的较小值。

#### Scenario: Memory has priority under budget pressure
- **WHEN** memory 和 knowledge 结果合计超出预算
- **THEN** 系统优先保留 memory 内容
- **AND** 截断或省略低优先级 knowledge 内容

#### Scenario: Sources only include injected content
- **WHEN** 某条 memory 或 knowledge 结果因预算不足未被注入
- **THEN** `BuiltContext.sources` 不包含该结果的来源摘要

### Requirement: Agent runtime uses long-term context
agent-runtime SHALL 在构造 agent prompt 前调用 long-term-ctx，并只在 `BuiltContext.text` 非空时追加长期上下文区段。

#### Scenario: Agent prompt includes long-term context
- **WHEN** `build_context()` 返回非空 `text`
- **THEN** agent-runtime 将该文本加入本次 agent prompt

#### Scenario: Empty context is omitted
- **WHEN** `build_context()` 返回空 `text`
- **THEN** agent-runtime 不追加空的长期上下文区段

### Requirement: Long-term context evaluation fixtures
系统 SHALL 提供 deterministic long-term context evaluation fixtures，用于验证 memory / knowledge
context 是否按预期注入 agent prompt。

#### Scenario: Fixture schema is explicit
- **WHEN** evaluation runner 加载 fixture
- **THEN** fixture 包含 name、user_id、agent_id、query、available_tokens、memories、knowledge、
  expected_text、forbidden_text、expected_sources 和 forbidden_sources

#### Scenario: Invalid fixture is rejected
- **WHEN** fixture 缺失必需字段或 source assertion 格式非法
- **THEN** evaluation runner 报告 fixture validation failure

### Requirement: Deterministic long-term context evaluation
系统 SHALL 默认使用 fake memory 和 fake knowledge provider 运行 long-term context evaluation，
保证评估稳定且不依赖真实外部服务。

#### Scenario: Runner injects fake provider results
- **WHEN** evaluation case 运行
- **THEN** runner 使用 fixture 中的 fake memory 和 fake knowledge provider results 调用 `build_context()`

#### Scenario: Expected text is validated
- **WHEN** evaluation case 运行完成
- **THEN** runner 验证 expected_text snippets 出现在 `BuiltContext.text`

#### Scenario: Forbidden text is rejected
- **WHEN** evaluation case 运行完成
- **THEN** runner 验证 forbidden_text snippets 不出现在 `BuiltContext.text`

#### Scenario: Expected sources are validated
- **WHEN** evaluation case 运行完成
- **THEN** runner 验证 expected_sources 出现在 `BuiltContext.sources`

#### Scenario: Forbidden sources are rejected
- **WHEN** evaluation case 运行完成
- **THEN** runner 验证 forbidden_sources 不出现在 `BuiltContext.sources`

#### Scenario: Evaluation is isolated from production data
- **WHEN** 默认 evaluation case 运行
- **THEN** runner 不调用真实 LLM、embedding provider、KB connector 或 SaaS
- **AND** runner 不触碰 `data/`

### Requirement: Optional real-provider long-term context smoke
系统 SHALL 提供显式启用的真实 provider long-term context smoke 入口，且默认跳过。

#### Scenario: Real provider smoke is skipped by default
- **WHEN** 未设置 `FLEETENT_EVAL_REAL_LONG_TERM_CONTEXT=1`
- **THEN** real provider smoke case 被 skip

#### Scenario: Real provider smoke requires explicit configuration
- **WHEN** 设置 `FLEETENT_EVAL_REAL_LONG_TERM_CONTEXT=1` 但缺少 provider credentials 或配置
- **THEN** real provider smoke case 被 skip

#### Scenario: Real provider smoke is manually runnable
- **WHEN** 设置 `FLEETENT_EVAL_REAL_LONG_TERM_CONTEXT=1` 且 provider 配置完整
- **THEN** runner 可以使用真实 provider 运行 smoke fixture

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
