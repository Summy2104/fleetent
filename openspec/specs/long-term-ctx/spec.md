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

`build_context()` SHALL 先通过 `list_always_facts(user_id)` 无条件注入所有 `scope='always'` facts（独立 section，置于其他 memory 之前），再调用 `search_facts()` 语义检索 `scope='situational'` facts 并将结果格式化为 memory 区段。

#### Scenario: Always facts injected unconditionally
- **WHEN** 用户存在 `scope='always'` facts
- **THEN** `BuiltContext.text` 包含 `[Behavioral directives]` 区段
- **AND** 该区段出现在 `[Long-term memory]` 区段之前
- **AND** 该区段内容与当前用户 query 语义无关也必须存在

#### Scenario: Always facts injected even with zero situational hits
- **WHEN** 向量检索无 `situational` facts 命中，但存在 `always` facts
- **THEN** `BuiltContext.text` 包含 `[Behavioral directives]` 区段
- **AND** `BuiltContext.sources` 包含 `source_type="memory"` 的来源摘要

#### Scenario: Empty always facts omits directives section
- **WHEN** 用户无 `scope='always'` facts
- **THEN** `BuiltContext.text` 不包含空的 `[Behavioral directives]` 区段

#### Scenario: Situational facts still retrieved by vector search
- **WHEN** `build_context()` 被调用
- **THEN** `search_facts()` 仍被调用以检索 `situational` facts
- **AND** 两类 facts 分别渲染为独立区段

#### Scenario: Memory results are included
- **WHEN** `search_facts()` 返回相关 situational memory items
- **THEN** `BuiltContext.text` 包含 `[Long-term memory]` 区段
- **AND** `BuiltContext.sources` 包含 `source_type="memory"` 的来源摘要

#### Scenario: Empty situational memory results are omitted
- **WHEN** `search_facts()` 返回空结果
- **THEN** `BuiltContext.text` 不包含空的 `[Long-term memory]` 区段

### Requirement: Optional knowledge provider
系统 SHALL 将 KB 检索作为可替换的 knowledge provider,经一个正式契约访问:
`(principal: Principal, query: str, kb_ids: list[str], limit: int, audit: KBRetrievalAuditContext | None) → list[KnowledgeChunk]`。
系统 SHALL 提供两个 built-in provider 实现:默认 `LocalKnowledgeProvider`(读本地 knowledge-base、按 agent retrieval_policy 跑检索),以及 `HttpKnowledgeProvider`(经 HTTP 调一个远程 KB 检索端点)。`HttpKnowledgeProvider` SHALL 按一份中立 wire 协议工作——请求体 `{principal:{user_id, tenant_id}, query, kb_ids, limit}`,响应体 `{chunks: [KnowledgeChunk JSON]}`——并以 Bearer service key + `X-Fleetent-Principal` header 鉴权(复用 `identity.encode_ingress_principal`);自家 KB 服务与外部系统实现同一份协议,无特权内部路径。
系统 SHALL 允许经 `set_knowledge_provider` 注入替换 provider,注入的 provider SHALL 按同一契约接收 principal、fleetent 解析好的 kb_ids 与 audit。knowledge provider 未启用、未配置、返回空结果、超时或抛错(含 HTTP 错误/网络故障)时,long-term-ctx 仍正常返回可用上下文(失败降级为空结果)。

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

#### Scenario: Default provider preserves current behavior
- **WHEN** 未注入自定义 provider 且 `knowledge_base.enabled=true`
- **THEN** long-term-ctx 经默认 `LocalKnowledgeProvider` 检索
- **AND** 结果与直接调用 `knowledge_base.search()` / planner(按 retrieval_policy)等价
- **AND** provider 返回的 source id 对应 chunk id

#### Scenario: Injected provider receives full scope
- **WHEN** 经 `set_knowledge_provider` 注入了自定义 provider
- **THEN** long-term-ctx 以 `(principal, query, kb_ids, limit, audit)` 调用它
- **AND** principal 含 tenant_id 与 user_id、kb_ids 为 fleetent 按 agent 绑定解析后的范围、audit 被透传
- **AND** 返回类型为 `list[KnowledgeChunk]`

#### Scenario: HttpKnowledgeProvider retrieves over the wire protocol
- **WHEN** 配置为 `HttpKnowledgeProvider` 且远程 KB 端点可用
- **THEN** provider 以 `{principal, query, kb_ids, limit}` POST 到配置的 endpoint,带 Bearer service key 与 `X-Fleetent-Principal` header
- **AND** 把响应 `{chunks: [...]}` 反序列化为 `list[KnowledgeChunk]` 返回给 long-term-ctx 预算管线

#### Scenario: Provider failure degrades to empty
- **WHEN** knowledge provider 超时或抛出异常(含 HttpKnowledgeProvider 的 HTTP 错误 / 网络故障)
- **THEN** long-term-ctx 记日志并将该路径降级为空结果
- **AND** `build_context()` 不抛出、不中断回复

### Requirement: Agent memory context retrieval

`build_context()` SHALL 调用 `memory.search_agent_memory(query, limit)` 检索该 agent 的 agent memory，并将结果作为 `source_type="agent_memory"` 的候选源并入上下文。agent memory 为 **per-agent**（非 per-user），检索 **MUST NOT** 传 `user_id`（隔离由 per-agent 物理库提供）。空结果 SHALL 省略该区段。

#### Scenario: Agent memory results are included

- **WHEN** `search_agent_memory` 返回相关 agent memory items
- **THEN** `BuiltContext.text` 包含 agent_memory 区段
- **AND** `BuiltContext.sources` 包含 `source_type="agent_memory"` 的来源摘要

#### Scenario: Empty agent memory results are omitted

- **WHEN** `search_agent_memory` 返回空结果
- **THEN** `BuiltContext.text` 不包含空的 agent_memory 区段

#### Scenario: Agent memory retrieval is per-agent, not per-user

- **WHEN** `build_context()` 检索 agent memory
- **THEN** 调用 `search_agent_memory` 不携带 `user_id`（对该 agent 的所有 user 共享）

### Requirement: Context merge and budget control
系统 SHALL 合并 memory、agent_memory 与 knowledge 三类源结果，并保证注入文本不超过可用 token 预算与配置上限中的较小值。三类源各有**独立预算档**：`memory_max_tokens` / `agent_memory_max_tokens` / `knowledge_max_tokens` 与各自的 `top_k`。`conflict_preference` SHALL 支持三方取向（memory / agent_memory / knowledge / auto），决定预算压力下的优先级。

#### Scenario: 各源在各自预算档内选择

- **WHEN** 某一类源（memory / agent_memory / knowledge）的候选超过其 `*_max_tokens` 或 `*_top_k`
- **THEN** 系统在该源的独立预算/条数档内截断，不挤占其它源的预算档

#### Scenario: Memory has priority under budget pressure
- **WHEN** 三类源结果合计超出总预算
- **THEN** 系统按 `conflict_preference` 决定保留优先级（默认 memory 优先于 knowledge）
- **AND** 截断或省略低优先级内容

#### Scenario: Sources only include injected content
- **WHEN** 某条 memory / agent_memory / knowledge 结果因预算不足未被注入
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

### Requirement: Long-term context uses agent KB bindings
long-term-ctx SHALL 从 agent 配置中**已 materialize 的 KB bindings**（`agent.knowledge`，源自平台 `agent_kbs`，见 `kb-agent-binding`）解析 agent 的有效 KB 范围(kb_ids 与 tenant_id),并经 knowledge provider 契约把该范围传入 provider；provider 只检索该范围内的知识库内容。作用域解析 SHALL 由 long-term-ctx 完成(provider-agnostic),long-term-ctx MUST NOT 依赖 knowledge_base 模块的运行时绑定表/解析器。

#### Scenario: Long-term-ctx resolves KB scope and passes it to the provider
- **WHEN** `knowledge_base.enabled=true` 且 long-term-ctx 准备检索 KB
- **THEN** long-term-ctx 从 `agent.knowledge`（已 materialize 的 bindings）解析有效 `kb_ids` 与 `tenant_id`
- **AND** 以 `(principal, query, kb_ids, limit, audit)` 调用 knowledge provider，kb_ids 为解析后的范围

#### Scenario: Single-tenant scope invariant
- **WHEN** 解析 agent 的 KB 范围
- **THEN** 所有 binding 共享同一 tenant_id（与 agent-knowledge-config 的单租户不变量一致），principal.tenant_id 取该值

#### Scenario: Empty KB scope degrades without calling provider
- **WHEN** `agent.knowledge` 无任何 KB binding（或 `knowledge_base.enabled=false`）
- **THEN** long-term-ctx 不调用 knowledge provider
- **AND** `build_context()` 仍按现有规则返回 memory context 或空 context
- **AND** agent-runtime 不因 KB 范围为空而失败

### Requirement: 并发检索

`build_context()` SHALL 并发执行 memory、knowledge、agent_memory 三路检索（而非顺序等待），整体检索延迟不超过最慢一路。各路返回结果后的合并、排序与预算控制语义不变。

#### Scenario: 三路并发而非顺序

- **WHEN** `build_context()` 触发三路检索，其中每路检索人为延迟 D
- **THEN** 三路检索的总耗时约为 D（最慢一路），而非约 3×D（顺序之和）

#### Scenario: 单路结果不依赖其他路完成

- **WHEN** 某一路检索快速返回、另一路较慢
- **THEN** 快路结果不被慢路阻塞，最终合并结果包含所有已成功返回路的结果

### Requirement: 单路检索超时降级

每路检索 SHALL 受单路超时约束（由配置 `retrieval_timeout_seconds` 控制，默认 5 秒）。某路超时 SHALL 降级为该路空结果、记一条 `warning` 级日志，并 MUST NOT 阻塞其余路或使 `build_context()` 抛出异常。超时路在后续合并中等价于该路返回空。

#### Scenario: 单路超时降级为空结果

- **WHEN** memory 检索耗时超过 `retrieval_timeout_seconds`
- **THEN** memory 路被视为空结果，knowledge 与 agent_memory 路正常并入上下文，`build_context()` 正常返回，不抛异常

#### Scenario: 超时记录可观测日志

- **WHEN** 某路检索超时被降级
- **THEN** 系统记录一条 `warning` 日志，标明超时的检索路名称

#### Scenario: 全部超时返回空上下文

- **WHEN** 三路检索均超时
- **THEN** `build_context()` 返回空 `BuiltContext`（`text` 为空、`sources` 为空），与"三路均无结果"行为一致

### Requirement: 检索分段计时可观测

`build_context()` SHALL 为每路检索记录耗时与是否超时，使"哪一路慢"可从结构化日志/trace 直接判定，无需复现。

#### Scenario: 每路记录耗时

- **WHEN** `build_context()` 完成一次检索
- **THEN** memory、knowledge、agent_memory 三路各自的耗时（毫秒/秒）与超时标志被记录到结构化日志或 trace

