## ADDED Requirements

### Requirement: 未完成任务在压缩后逐字保留（active-task 续跑块）

当压缩丢弃中段（生成摘要或静态降级）时，压缩 SHALL 把该 session 的未完成任务（状态非 `completed` 的 todo 条目，读自 agent 侧 `{session_id}.todo`）作为一条逐字保留的 system 块注入压缩结果，注入位置在头部之后、摘要/降级提示之前（顺序为「头部 → active-task 块 → 摘要 → 尾部」）。该块 MUST 逐字保留任务文本（不摘要、不改写）；其 token MUST 计入尾部保留的预算投影。无 `session_id`、无未完成任务、或读取 `.todo` 失败时 MUST NOT 注入该块且 MUST NOT 报错（行为与未引入本能力时一致）。本能力 MUST NOT 新增持久化结构（复用 C2 的 `.todo`），MUST NOT 依赖 platform。

#### Scenario: 有未完成任务时压缩后逐字保留
- **WHEN** session 存在未完成 todo（pending/in_progress）且压缩生成了摘要
- **THEN** 压缩结果在头部之后、摘要之前含一条逐字列出这些未完成任务的 system 块

#### Scenario: 无未完成任务时不注入
- **WHEN** session 无未完成 todo（为空或全部 completed）而触发压缩
- **THEN** 压缩结果不含 active-task 块，序列与未引入本能力时一致

#### Scenario: 无 session 或读取失败时安全退化
- **WHEN** 压缩无 `session_id`，或读取 `.todo` 失败
- **THEN** 不注入 active-task 块、不报错，压缩正常完成且序列对 LLM 合法
