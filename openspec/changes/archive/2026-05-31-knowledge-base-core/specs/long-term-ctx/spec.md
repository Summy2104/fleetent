## MODIFIED Requirements

### Requirement: Optional knowledge provider
系统 SHALL 将 knowledge-base 作为可选 provider；knowledge-base 未实现、未启用或返回空结果时，
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
