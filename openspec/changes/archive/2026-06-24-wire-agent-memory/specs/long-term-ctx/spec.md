## ADDED Requirements

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

## MODIFIED Requirements

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
