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
