## MODIFIED Requirements

### Requirement: Optional knowledge provider
系统 SHALL 将 KB 检索作为可替换的 knowledge provider,经一个正式契约访问:
`(principal: Principal, query: str, kb_ids: list[str], limit: int, audit: KBRetrievalAuditContext | None) → list[KnowledgeChunk]`。
系统 SHALL 提供默认 built-in `LocalKnowledgeProvider`(读本地 knowledge-base、按 agent retrieval_policy 跑检索),
并 SHALL 允许经 `set_knowledge_provider` 注入替换 provider,注入的 provider SHALL 按同一契约接收 principal、
fleetent 解析好的 kb_ids 与 audit。knowledge provider 未启用、未配置、返回空结果、超时或抛错时,
long-term-ctx 仍正常返回可用上下文(失败降级为空结果)。

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

#### Scenario: Provider failure degrades to empty
- **WHEN** knowledge provider 超时或抛出异常
- **THEN** long-term-ctx 记日志并将该路径降级为空结果
- **AND** `build_context()` 不抛出、不中断回复

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
