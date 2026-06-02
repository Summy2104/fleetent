## ADDED Requirements

### Requirement: Long-term context uses agent KB bindings
long-term-ctx SHALL 通过 knowledge-base public API 解析 agent 的 KB 范围，并只检索该范围内的知识库内容。

#### Scenario: Built-in provider resolves agent KB scope
- **WHEN** `knowledge_base.enabled=true`
- **AND** long-term-ctx built-in knowledge provider 准备检索 KB
- **THEN** provider 调用 `knowledge_base.resolve_agent_kb_ids(tenant_id, agent_id)`

#### Scenario: Built-in provider searches resolved KBs
- **WHEN** `resolve_agent_kb_ids()` 返回一个或多个 KB id
- **THEN** provider 调用 `knowledge_base.search(query, tenant_id, kb_ids, limit, mode)`
- **AND** `kb_ids` 使用解析后的 KB 列表

#### Scenario: Empty KB scope degrades without search
- **WHEN** `resolve_agent_kb_ids()` 返回空列表
- **THEN** provider 不调用 `knowledge_base.search()`
- **AND** `build_context()` 仍按现有规则返回 memory context 或空 context
- **AND** agent-runtime 不因 KB 范围为空而失败
