## MODIFIED Requirements

### Requirement: todo 维护 session 级任务列表

`todo` SHALL 接受 `action`（`Literal["set", "update", "get", "clear"]`）参数维护 session 级任务列表；任务条目为 `{id, text, status}`，`status` ∈ `pending` / `in_progress` / `completed`，且任意时刻至多一个条目处于 `in_progress`。`set` 接受 `items`（`list[str]`）替换整个列表，每项自动赋唯一 `id` 与 `pending` 状态；`update` 接受 `item_id` 与目标 `status` 修改指定条目；`get` 返回当前列表（含状态）；`clear` 清空。任务列表 MUST 持久化到 agent 侧 `{session_id}.todo` 兄弟文件（JSON 内容），跨进程重启存活；持久化 MUST 为原子写（`tmp→rename`）且 MUST NOT 获取 `session_lock`（避免与运行中持锁的 agent 循环死锁）；MUST NOT 依赖 platform、MUST NOT 写入数据库或 session JSON 的 `meta`。无 `session_id` 时降级为进程内临时列表（不报错、不持久化）。

#### Scenario: 设置任务列表
- **WHEN** 调用 `todo(action="set", items=["处理文件A", "处理文件B"])`
- **THEN** 列表被替换为两个条目，各自获得唯一 id 与 `pending` 状态，返回确认信息

#### Scenario: 标记任务进行中
- **WHEN** 对某 `pending` 条目调用 `todo(action="update", item_id=<id>, status="in_progress")`
- **THEN** 该条目状态变为 `in_progress`，返回确认信息

#### Scenario: 至多一个 in_progress
- **WHEN** 已有条目处于 `in_progress`，再对另一条目 `update` 为 `in_progress`
- **THEN** 操作被拒绝并返回提示（需先完成当前进行中的条目），列表状态不变

#### Scenario: 完成任务
- **WHEN** 对某条目调用 `todo(action="update", item_id=<id>, status="completed")`
- **THEN** 该条目状态变为 `completed`，返回确认信息

#### Scenario: 查询当前任务列表（含状态）
- **WHEN** 调用 `todo(action="get")`
- **THEN** 返回当前列表，每条含 id、文本与状态；列表为空时返回空列表提示

#### Scenario: 清空任务列表
- **WHEN** 调用 `todo(action="clear")`
- **THEN** 列表清空，`{session_id}.todo` 文件被删除，返回确认信息

#### Scenario: 任务列表跨进程重启存活
- **WHEN** 在某 session 设置任务后进程重启，再以同一 `session_id` 调用 `todo(action="get")`
- **THEN** 返回重启前持久化的任务列表（从 `{session_id}.todo` 读回）

#### Scenario: 无 session_id 时降级为临时列表
- **WHEN** 工具调用缺少 `session_id`（如无会话的一次性调用）
- **THEN** todo 在进程内临时维护、不写文件、不报错
