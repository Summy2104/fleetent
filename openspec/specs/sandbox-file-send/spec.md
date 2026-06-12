# sandbox-file-send Specification

## Purpose
TBD - created by archiving change sandbox-file-egress. Update Purpose after archive.
## Requirements
### Requirement: send_file 工具发送 workspace 产物给固定收件人

系统 SHALL 提供宿主侧内置工具 `send_file(path)`，把沙箱 workspace 产物作为文件附件送回当前对话的发起人。`path` MUST 是 **workspace 相对路径**（沙箱优先执行的单根 `/workspace` 坐标系），工具 MUST 经 `SandboxManager.workspace_host_path(scope, session_id, agent_name)` 求出宿主 workspace 根目录、再经 workspace 相对路径翻译（`resolve_host_path`，与文件工具宿主围栏同一翻译）解析为宿主真实文件后读取字节发出。翻译 MUST 拒绝逃出 workspace 的路径（`..` 越界），越界 MUST 返回说明文本而非发送。

`send_file` 的收件人 MUST 由 harness 从 `tool_context.session_context` 固定（`platform` + `sender_id`），MUST NOT 接受任何由模型提供的收件人参数。对 LLM 暴露的参数 MUST 只有 `path`（`tool_context` 为 out-of-band 注入，不进 LLM schema）。这是 `send_file` 区别于 `send_im_message`（收件人由模型任意指定、故保持 medium gated）的核心安全契约。

#### Scenario: 相对路径产物发回当前发起人

- **WHEN** agent 在 DM 会话调用 `send_file(path="report.pdf")`，且 workspace 内存在该文件
- **THEN** 工具按 `session_context` 的 `platform`/`sender_id` 解析宿主真实文件并作为附件发回该发起人，结果文本回显**实际收件人**（`platform:sender_id`）

#### Scenario: 路径逃出 workspace 被拒

- **WHEN** agent 调用 `send_file(path="../../etc/passwd")`
- **THEN** 路径翻译判定越界，工具 MUST NOT 读取或发送该文件，返回说明越界的文本

#### Scenario: 收件人不取模型参数

- **WHEN** 模型在 `send_file` 调用中尝试夹带任意收件人/目标字段
- **THEN** 该字段不在工具 schema 内、不被采纳，收件人仍只来自 `session_context`

### Requirement: send_file 免审批当且仅当盒子封闭且收件人受约束

`send_file` 免审批（不经 permission gate 直跑发送）MUST 当且仅当三条同时成立：`workspace_scope == session`（会话级隔离工作区）∧ 当前会话为 `dm`（`session_context.chat_type == "dm"`）∧ `session_context` 非空。任一不成立时，工具 MUST **fail-closed**：不发送文件，返回显式说明文本，引导改用经 medium 审批的 `send_im_message` 路径。

该免审批正当性绑定"收件人受约束 + 会话级封闭"：收件人由 harness 固定（无模型可控的不可信目标）、且仅在会话私有工作区 + 私信场景自动外发；故 `send_file` 以 registry `risk_level` 直跑（action gate 给 `DIRECT`），其条件门控由工具体内前置条件实现，**MUST NOT 改 `resolve_action_mode` 契约、MUST NOT 改 registry 既有 risk 常量、MUST NOT 新增 action gate 动态 risk 缝**。

#### Scenario: 会话私信封闭时免审批直发

- **WHEN** `workspace_scope == session`、当前会话为 `dm`、`session_context` 非空，agent 调用 `send_file(path="out.csv")`
- **THEN** 工具不经审批直接发送，结果回显实际收件人

#### Scenario: 频道会话 fail-closed

- **WHEN** 当前会话为频道（`chat_type == "channel"`），agent 调用 `send_file`
- **THEN** 工具 MUST NOT 自动外发，返回说明文本引导改用经审批的 `send_im_message`

#### Scenario: agent scope 工作区 fail-closed

- **WHEN** `workspace_scope == agent`（跨会话复用工作区），agent 调用 `send_file`
- **THEN** 工具 MUST NOT 自动外发，返回说明文本（非会话私有工作区不满足免审批前提）

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

