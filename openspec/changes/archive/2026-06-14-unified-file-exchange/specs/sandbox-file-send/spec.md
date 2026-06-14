# sandbox-file-send Delta

## MODIFIED Requirements

### Requirement: send_file 工具发送 workspace 产物给固定收件人

系统 SHALL 提供宿主侧内置工具 `send_file(path)`，把工件作为文件附件送回当前对话的发起人。`path` MUST 在双根命名空间内解释：**workspace 相对路径**（沙箱优先执行的单根 `/workspace` 坐标系，经 `SandboxManager.workspace_host_path(scope, session_id, agent_name)` + `resolve_host_path` 翻译，与文件工具宿主围栏同一翻译）；或 **`/exchange/<server_id>/...` 规范路径**（经 file-exchange 归属校验解析到有效文件根内真实文件）。翻译 MUST 拒绝两根之外与 `..` 越界路径，越界 MUST 返回说明文本而非发送。

`send_file` 的收件人 MUST 由 harness 从 `tool_context.session_context` 固定（`platform` + `sender_id`），MUST NOT 接受任何由模型提供的收件人参数。对 LLM 暴露的参数 MUST 只有 `path`（`tool_context` 为 out-of-band 注入，不进 LLM schema）。这是 `send_file` 区别于 `send_im_message`（收件人由模型任意指定、故恒 medium gated）的核心安全契约。

#### Scenario: 相对路径产物发回当前发起人

- **WHEN** agent 在 DM 会话调用 `send_file(path="report.pdf")`，且 workspace 内存在该文件
- **THEN** 工具按 `session_context` 的 `platform`/`sender_id` 解析宿主真实文件并作为附件发回该发起人，结果文本回显**实际收件人**（`platform:sender_id`）

#### Scenario: 本 scope /exchange 工件直发

- **WHEN** agent 在 DM 会话调用 `send_file(path="/exchange/google-drive/report.xlsx")`，该工件台账 `scope_key` == 当前 run scope_key
- **THEN** 工具解析有效文件根内真实文件并发回当前发起人

#### Scenario: 路径逃出命名空间被拒

- **WHEN** agent 调用 `send_file(path="../../etc/passwd")` 或一个两根之外的绝对路径
- **THEN** 路径翻译判定越界，工具 MUST NOT 读取或发送该文件，返回说明越界的文本

#### Scenario: 收件人不取模型参数

- **WHEN** 模型在 `send_file` 调用中尝试夹带任意收件人/目标字段
- **THEN** 该字段不在工具 schema 内、不被采纳，收件人仍只来自 `session_context`

### Requirement: send_file 免审批当且仅当盒子封闭且收件人受约束

`send_file` 免审批（不经 permission gate 直跑发送）MUST 当且仅当四条同时成立：回当前会话（收件人由 harness 固定）∧ 当前会话为 `dm`（`session_context.chat_type == "dm"`）∧ 文件全为本 run scope 归属（workspace 相对路径**恒为本 scope 私有**——它就是按当前 run 的 scope_key 键控的；或 `/exchange` 工件台账 `scope_key` == 当前 run scope_key）∧ `session_context` 非空（交互上下文）。

任一条件不成立且 `session_context` 非空时，工具 MUST **升级为 medium 审批**而非拒绝：经 permission gate 走与 `send_im_message` 同级的审批流程，批准后发送、拒绝后不发送——既有"fail-closed 拒绝并指引换工具"的行为由"同一调用自动升级审批"取代。免审批/升级的判定 SHALL 经注册表的参数化风险（callable `risk_level`，见 permission-gate delta）在调用期求值；`sandbox-file-send` 原"MUST NOT 新增 action gate 动态 risk 缝"约束由本变更取代。

免审批正当性绑定"收件人受约束 + scope 级封闭"：收件人由 harness 固定（无模型可控的不可信目标）、文件为本 run scope 私有产物、且在私信场景。多人部署 `workspace_scope` 被强制为 session，故"本 scope 归属"即"本会话归属"，不放大可发面；单人 `workspace_scope: agent` 下唯一发起人即文件所有者，agent 级私有文件直发亦不泄漏。`session_context` 为 `None` 的路径不在本要求范围（按既有"无会话上下文的运行路径一律 fail-closed"要求处理，不升级审批——该路径无收件人可言且无审批回路）。

#### Scenario: 会话私信封闭时免审批直发

- **WHEN** 四条件全部成立（DM、本 scope 文件、交互上下文、回当前会话），agent 调用 `send_file(path="out.csv")`
- **THEN** 工具不经审批直接发送，结果回显实际收件人

#### Scenario: 频道会话升级审批

- **WHEN** 当前会话为频道（`chat_type == "channel"`），agent 调用 `send_file`
- **THEN** 该调用经 permission gate 弹出 medium 审批；批准后文件发出，拒绝后不发送

#### Scenario: agent scope 本 scope 文件免审批直发

- **WHEN** 单人部署 `workspace_scope == agent`，DM 会话中 agent 调用 `send_file` 发送本 scope 私有产物（workspace 相对路径或本 scope `/exchange` 工件）
- **THEN** 工具不经审批直接发送（与 `/workspace` 一致：唯一发起人即所有者，不因 scope 为 agent 而被一刀升级或拒绝）

#### Scenario: 跨 scope /exchange 工件升级审批

- **WHEN** agent 调用 `send_file` 引用台账 `scope_key` 不等于当前 run 的 `/exchange` 工件
- **THEN** 该调用升级 medium 审批；批准即跨 scope 授权，文件发回当前发起人
