# sandbox-file-send Specification

## Purpose
TBD - created by archiving change sandbox-file-egress. Update Purpose after archive.
## Requirements
### Requirement: send_file 工具发送 workspace 产物给固定收件人

系统 SHALL 提供宿主侧内置工具 `send_file(path)`，把工件作为文件附件送回**当前对话**。`path` MUST 在双根命名空间内解释：**workspace 路径**（沙箱优先执行的单根 `/workspace` 坐标系，经 `SandboxManager.workspace_host_path(scope, session_id, agent_name)` + `resolve_host_path` 翻译，与文件工具宿主围栏同一翻译）——既接受 **workspace 相对路径**（如 `report.xlsx`），也接受**容器 `/workspace[/<rel>]` 绝对路径**（如 `/workspace/outbound/report.xlsx`，剥去 `/workspace` 挂载点前缀后按宿主 root 解析，与模型所见的单根坐标系一致）；或 **`/exchange/<server_id>/...` 规范路径**（经 file-exchange 归属校验解析到有效文件根内真实文件）。翻译 MUST 拒绝两根之外、`..` 越界、以及 `/workspace` 仿冒前缀（如 `/workspace-evil/...`）路径，越界 MUST 返回说明文本而非发送。

`send_file` 的收件人 MUST 由 harness 固定为**当前对话地址**，MUST NOT 接受任何由模型提供的收件人参数。对 LLM 暴露的参数 MUST 只有 `path`（`tool_context` 为 out-of-band 注入，不进 LLM schema）。当 `tool_context` 携带权威对话地址（`conversation_address`，含 `platform`/`chat_id`/`target_type`/`thread_id`，与文本回复同源）时，收件人 MUST 解析为该地址：当前会话为频道则文件 SHALL 发回该频道（`target_type="channel"`，并挂回 inbound thread）、为私信则发回该私信用户——即文件落到与文本回复完全相同的位置。当不携带对话地址（如 standalone CLI / 流式 / 无网关路径）时，收件人 MUST 回退为 `session_context` 的 `platform` + `sender_id` 私信（向后兼容旧行为）。收件人由 harness 固定而非模型可控，是 `send_file` 区别于 `send_im_message`（收件人由模型任意指定、故按接收方身份轴判审批）的核心安全契约。

#### Scenario: 容器 /workspace 绝对路径被接受

- **WHEN** agent 调用 `send_file(path="/workspace/outbound/report.xlsx")`（模型在容器单根坐标系下产出的绝对路径），且该文件在 workspace 内真实存在
- **THEN** 路径翻译剥去 `/workspace` 前缀按宿主 root 解析到该文件，工具按当前对话地址将其作为附件发回（与传 `outbound/report.xlsx` 相对路径等效）

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

- **WHEN** agent 调用 `send_file(path="../../etc/passwd")`、一个两根之外的绝对路径，或 `/workspace-evil/x` 仿冒前缀
- **THEN** 路径翻译判定越界，工具 MUST NOT 读取或发送该文件，返回说明越界的文本

#### Scenario: 收件人不取模型参数

- **WHEN** 模型在 `send_file` 调用中尝试夹带任意收件人/目标字段
- **THEN** 该字段不在工具 schema 内、不被采纳，收件人仍只来自 harness 注入的对话地址

### Requirement: 无会话上下文的运行路径一律 fail-closed

当 `tool_context.session_context` 为 `None` 时，`send_file` MUST fail-closed：不发送文件，返回说明"当前运行路径无会话发起人，无法自动外发文件"的文本。该约束 MUST 覆盖 scheduled task、sub_agent、`invoke_agent` 等 `session_context = None` 的运行路径——这些路径没有可固定的当前发起人，自动外发会指向不确定收件人。

#### Scenario: scheduled task 路径 fail-closed

- **WHEN** 一个 scheduled task 运行时（`session_context = None`）的 agent 调用 `send_file`
- **THEN** 工具 MUST NOT 发送，返回无会话发起人的说明文本

#### Scenario: sub_agent / invoke_agent 路径 fail-closed

- **WHEN** sub_agent 或经 `invoke_agent` 内部调用的 agent（`session_context = None`）调用 `send_file`
- **THEN** 工具 MUST NOT 发送，返回无会话发起人的说明文本

### Requirement: send_file 在无连接器或投递失败时返回说明文本且不抛

`send_file` MUST 永不抛异常。运行路径无可用 IM 连接器（如 CLI/HTTP 路径，`outbound_connectors` 为空或缺当前平台连接器）、目标平台不支持出站文件、文件不存在/读取失败、或出站投递失败时，工具各 MUST 返回一条解释性文本结果，MUST NOT 中断 agent 运行。该降级保证 agent 在无 platform、无 IM 网关环境下仍能完成 `fleetent agent run`。

#### Scenario: CLI/HTTP 路径无连接器

- **WHEN** `send_file` 在没有 IM 连接器的运行路径（`outbound_connectors` 为空）被调用
- **THEN** 工具返回说明"当前通道不支持主动外发文件"的文本，不抛异常

#### Scenario: 出站投递失败优雅降级

- **WHEN** 连接器存在但底层出站文件投递抛错（网络/权限）
- **THEN** 工具捕获失败，返回说明投递失败、可稍后重试的文本，不向上抛

