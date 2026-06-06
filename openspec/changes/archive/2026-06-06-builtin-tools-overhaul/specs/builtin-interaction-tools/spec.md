## ADDED Requirements

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
`todo` SHALL 接受 `action`（`Literal["set", "get", "clear"]`）和 `items`（`list[str]`，`action="set"` 时必填）参数；在内存中维护 session 级别的任务列表；`set` 替换整个列表，`get` 返回当前列表，`clear` 清空；session 结束时自动释放，不持久化到数据库。

#### Scenario: 设置任务列表
- **WHEN** 调用 `todo(action="set", items=["处理文件A", "处理文件B", "生成报告"])`
- **THEN** session 任务列表被替换为指定内容，返回确认信息

#### Scenario: 查询当前任务列表
- **WHEN** 调用 `todo(action="get")`
- **THEN** 返回当前 session 任务列表；若为空返回 `"任务列表为空"`

#### Scenario: 清空任务列表
- **WHEN** 调用 `todo(action="clear")`
- **THEN** 任务列表清空，返回确认信息

#### Scenario: session 结束后任务列表自动清理
- **WHEN** session 结束（正常完成或超时）
- **THEN** 该 session 的 todo 列表从内存中删除，不影响其他 session
