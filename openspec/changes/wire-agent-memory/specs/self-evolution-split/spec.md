## ADDED Requirements

### Requirement: Agent memory proposal apply persists a row

当审批门 resolve 一个被批准的 agent memory proposal 时，回调的 agent memory 写接口 SHALL **真正写入一条 `agent_memory_items` 记录**（经 `memory.create_agent_memory`），并建立其向量索引——而非仅把 proposal 标记为 `applied`。content 取自 proposal 的 `proposed_content`，`source` SHALL 标为 `reflection_proposal`，`source_ref` SHALL 为该 proposal 的 id。该写入由 `governance` 编排（`governance → memory`，保持 `memory ↛ reflection` 护栏）。

#### Scenario: 批准的 agent memory proposal 真增行

- **WHEN** 一个 `target=agent_memory` 的 proposal 被审批通过并 resolve
- **THEN** `agent_memory_items` 表新增一条记录（content=proposal 的 proposed_content，source=`reflection_proposal`，source_ref=proposal id）
- **AND** 该记录的向量被索引（可被 `search_agent_memory` 检索）
- **AND** proposal 状态转为 `applied`

#### Scenario: 仅标记 applied 不算落地

- **WHEN** agent memory proposal 被批准
- **THEN** 系统 MUST NOT 在不写 `agent_memory_items` 的情况下把 proposal 标记为 `applied`（"落地"= 真写库 + 索引）
