# builtin-interaction-tools Specification

## Purpose
Agent 与用户交互工具集，提供暂停循环等待用户澄清（clarify）和 session 级任务列表管理（todo）能力。
## Requirements
### Requirement: clarify 暂停 agent 循环等待用户回答
`clarify` SHALL 接受 `question`（必填，问题文本）和 `choices`（可选，`list[str]`，提供时为选择题，否则为开放问答）参数；调用后通过 `user_input_gate` 暂停当前 session 的 agent 循环，直到用户回答或超时。返回用户的回答字符串；超时时返回 `"timeout: 用户未在 {N} 秒内回答"`，agent 可自行处理（继续、再问、使用默认值）。

#### Scenario: 开放式问答等待用户文字回复
- **WHEN** 调用 `clarify(question="请描述你期望的输出格式")`（无 choices）
- **THEN** agent 暂停，用户发送文字回复后继续，返回用户输入的字符串

#### Scenario: 选择题等待用户选择
- **WHEN** 调用 `clarify(question="如何处理重复记录？", choices=["跳过", "覆盖", "追加"])`
- **THEN** agent 暂停，用户选择后继续，返回所选选项文字（如 `"跳过"`）

#### Scenario: 超时后 agent 收到 timeout 结果
- **WHEN** 用户在默认 300 秒内未回答
- **THEN** 返回 `"timeout: 用户未在 300 秒内回答"`，agent 循环继续

### Requirement: clarify 在 IM 平台差异化渲染 choices
当 `choices` 非空时，IM 网关层 SHALL 按平台渲染交互组件：Slack 使用 Block Kit Actions（Button 元素）；Telegram 使用 `InlineKeyboardMarkup`；其他平台（WhatsApp、API、webhook 等）降级为编号文字列表。用户通过按钮点击或发送编号/文字回答，均路由至 `user_input_gate` 完成应答。

#### Scenario: Slack 渲染 Button 组件
- **WHEN** agent 在 Slack 会话中调用 `clarify` 且 `choices` 非空
- **THEN** Slack 收到带 Button 列表的 Block Kit 消息，用户点击后 `user_input_gate` 收到回答

#### Scenario: Telegram 渲染 InlineKeyboard
- **WHEN** agent 在 Telegram 会话中调用 `clarify` 且 `choices` 非空
- **THEN** Telegram 收到带 InlineKeyboardMarkup 的消息，用户点击后 `user_input_gate` 收到回答

#### Scenario: 非 IM 场景降级为文字 choices
- **WHEN** agent 通过 API/webhook 触发，无 IM 渲染层
- **THEN** 以编号文字列表呈现 choices，用户发送编号或文字回答均视为有效

### Requirement: clarify 使用独立 user_input_gate 通道
`clarify` 的等待机制 SHALL 由 `governance/user_input_gate.py` 模块提供，与 `permission_gate` 完全独立。`user_input_gate` 维护 session 级别的 `asyncio.Event` 和答案存储；IM 回调通过 `user_input_gate.answer(session_id, answer)` 触发 event；`clarify` 工具 `await` 该 event。

#### Scenario: user_input_gate 隔离于 permission_gate
- **WHEN** 同一 session 中同时有 `clarify` 等待和 `permission_gate` 审批
- **THEN** 两者互不干扰，各自的 event 独立触发

#### Scenario: session 结束时 gate 资源被清理
- **WHEN** session 正常结束或超时
- **THEN** 该 session 的 `user_input_gate` entry 被清理，不泄漏内存

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

