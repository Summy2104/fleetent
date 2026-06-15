## MODIFIED Requirements

### Requirement: send_file 工具发送 workspace 产物给固定收件人

系统 SHALL 提供宿主侧内置工具 `send_file(path)`，把工件作为文件附件送回**当前对话**。`path` MUST 在双根命名空间内解释：**workspace 相对路径**（沙箱优先执行的单根 `/workspace` 坐标系，经 `SandboxManager.workspace_host_path(scope, session_id, agent_name)` + `resolve_host_path` 翻译，与文件工具宿主围栏同一翻译）；或 **`/exchange/<server_id>/...` 规范路径**（经 file-exchange 归属校验解析到有效文件根内真实文件）。翻译 MUST 拒绝两根之外与 `..` 越界路径，越界 MUST 返回说明文本而非发送。

`send_file` 的收件人 MUST 由 harness 固定为**当前对话地址**，MUST NOT 接受任何由模型提供的收件人参数。对 LLM 暴露的参数 MUST 只有 `path`（`tool_context` 为 out-of-band 注入，不进 LLM schema）。当 `tool_context` 携带权威对话地址（`conversation_address`，含 `platform`/`chat_id`/`target_type`/`thread_id`，与文本回复同源）时，收件人 MUST 解析为该地址：当前会话为频道则文件 SHALL 发回该频道（`target_type="channel"`，并挂回 inbound thread）、为私信则发回该私信用户——即文件落到与文本回复完全相同的位置。当不携带对话地址（如 standalone CLI / 流式 / 无网关路径）时，收件人 MUST 回退为 `session_context` 的 `platform` + `sender_id` 私信（向后兼容旧行为）。收件人由 harness 固定而非模型可控，是 `send_file` 区别于 `send_im_message`（收件人由模型任意指定、故按接收方身份轴判审批）的核心安全契约。

#### Scenario: 频道会话文件发回频道

- **WHEN** agent 在频道会话调用 `send_file(path="report.xlsx")`，`tool_context.conversation_address` 解析为该频道（`target_type="channel"`、`chat_id` 为该频道、含 inbound `thread_id`），且 workspace 内存在该文件
- **THEN** 工具按对话地址将文件作为附件发回该频道并挂回该 thread，结果文本回显实际收件人（`platform:chat_id`）

#### Scenario: 私信会话文件发回私信

- **WHEN** agent 在 DM 会话调用 `send_file(path="report.pdf")`，`tool_context.conversation_address` 解析为该 DM（`target_type="user"`），且 workspace 内存在该文件
- **THEN** 工具将文件作为附件发回该 DM 用户，结果文本回显实际收件人

#### Scenario: 无对话地址时回退发起人私信

- **WHEN** agent 在无 `conversation_address` 的路径（如无 IM 网关注入对话地址）调用 `send_file`，但 `session_context` 非空
- **THEN** 工具回退按 `session_context` 的 `platform`/`sender_id` 作为私信收件人投递（旧行为），结果文本回显实际收件人

#### Scenario: 本 scope /exchange 工件直发

- **WHEN** agent 调用 `send_file(path="/exchange/google-drive/report.xlsx")`，该工件台账 `scope_key` == 当前 run scope_key
- **THEN** 工具解析有效文件根内真实文件并按当前对话地址发回

#### Scenario: 路径逃出命名空间被拒

- **WHEN** agent 调用 `send_file(path="../../etc/passwd")` 或一个两根之外的绝对路径
- **THEN** 路径翻译判定越界，工具 MUST NOT 读取或发送该文件，返回说明越界的文本

#### Scenario: 收件人不取模型参数

- **WHEN** 模型在 `send_file` 调用中尝试夹带任意收件人/目标字段
- **THEN** 该字段不在工具 schema 内、不被采纳，收件人仍只来自 harness 注入的对话地址

## REMOVED Requirements

### Requirement: send_file 免审批当且仅当盒子封闭且收件人受约束

**Reason**: 已被 `approval-boundary-redesign`（#259）取代——`approval-policy` 规定 `send_file` 恒免审批（`risk_for` 恒返回 `none`，因其无收件人参数、恒回当前对话）。本要求要求「频道会话升级审批」，既与现行代码不符，也与本次「频道→发频道」行为直接冲突。审批权威单一归 `approval-policy`。

**Migration**: 无代码迁移——代码早已恒免审批（`governance/approval_policy.py` 对 `send_file` 返回 `none`）。本次仅移除 spec 内残留的过时审批要求以消除矛盾；`send_file` 的免审批语义仍由 `approval-policy` 的「send_file 恒免审批」要求承载。
