## MODIFIED Requirements

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
