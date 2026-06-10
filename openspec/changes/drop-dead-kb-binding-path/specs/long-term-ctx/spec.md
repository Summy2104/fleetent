## MODIFIED Requirements

### Requirement: Long-term context uses agent KB bindings
long-term-ctx SHALL 从 agent 配置中**已 materialize 的 KB bindings**（`agent.knowledge`，源自平台 `agent_kbs`，见 `kb-agent-binding`）解析 agent 的有效 KB 范围，并只检索该范围内的知识库内容。long-term-ctx MUST NOT 依赖 knowledge_base 模块的运行时绑定表/解析器。

#### Scenario: Built-in provider resolves agent KB scope from agent.knowledge
- **WHEN** `knowledge_base.enabled=true`
- **AND** long-term-ctx built-in knowledge provider 准备检索 KB
- **THEN** provider 从 `agent.knowledge`（已 materialize 的 `AgentKnowledge` bindings）取该 agent 的有效 `kb_ids`

#### Scenario: Built-in provider searches resolved KBs
- **WHEN** `agent.knowledge` 含一个或多个 KB binding
- **THEN** provider 调用 `knowledge_base.search(query, tenant_id, kb_ids, limit, mode)`
- **AND** `kb_ids` 使用 `agent.knowledge` 解析后的 KB 列表

#### Scenario: Empty KB scope degrades without search
- **WHEN** `agent.knowledge` 无任何 KB binding（或 `knowledge_base.enabled=false`）
- **THEN** provider 不调用 `knowledge_base.search()`
- **AND** `build_context()` 仍按现有规则返回 memory context 或空 context
- **AND** agent-runtime 不因 KB 范围为空而失败
