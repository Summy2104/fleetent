# approval-policy Specification

## Purpose
TBD - created by archiving change approval-boundary-redesign. Update Purpose after archive.
## Requirements
### Requirement: 单一审批原则（接收方身份轴）经中心裁决入口

系统 SHALL 经唯一裁决入口 `governance/approval_policy.risk_for(tool_name, args, tool_context)` 判定工具风险档，且 MUST 遵循单一原则：**仅当 agent 主动把内容投递给「当前对话发起人以外的接收方」时**定级为 `medium`（审批）；回当前对话（同一 DM 用户或同一频道）与本地/沙箱内操作定级 `none`/`low`（免审批）。当前对话地址 MUST 取自 `tool_context.session_context`；无法解析当前对话地址时 MUST fail-closed 到 `medium`。`risk_for` MUST 是 action-gate 的风险来源——`runtime/loop.py` dispatch 与 `tools/registry.evaluate_risk_level` MUST 委托它；MUST NOT 依据 LLM 提供的 `tool_args` 字段降档（反逃逸）。对未被本策略特殊处理的工具，`risk_for` MUST 返回其注册静态风险档（如 `run_code` 维持 `medium`，其免审批由 `sandbox-containment-gating` 处置，本策略不覆盖）。`governance.approval_policy` MUST NOT `import fleetent.platform.*`。

#### Scenario: 外发给他人定级审批

- **WHEN** agent 调用 `send_im_message(target="U_OTHER", ...)`，`U_OTHER` 非当前对话发起人
- **THEN** `risk_for` 返回 `medium`，调用前置审批门

#### Scenario: 回当前对话免审批

- **WHEN** agent 调用 `send_im_message` 且 `(target, target_type)` 解析为当前对话地址（同一 DM 用户或同一频道）
- **THEN** `risk_for` 返回 `none`，直接执行无需审批

#### Scenario: send_file 恒免审批

- **WHEN** agent 调用 `send_file(path)`（无接收方参数，恒回当前对话）
- **THEN** `risk_for` 返回 `none`

#### Scenario: 无法解析对话地址时 fail-closed

- **WHEN** `tool_context.session_context` 缺失或当前对话地址不可解析，而被判工具属外发类
- **THEN** `risk_for` 返回 `medium`（宁可多一次审批）

#### Scenario: 非外发工具返回注册静态档

- **WHEN** `risk_for` 被查询 `run_code`
- **THEN** 返回其注册静态档 `medium`，由 sandbox-containment-gating 决定是否因封闭而免审批，本策略不改其档

#### Scenario: LLM 参数不能降档

- **WHEN** LLM 在 `tool_args` 放入 `risk`/`risk_level` 字段试图降低一个外发调用的等级
- **THEN** `risk_for` 忽略该字段，按系统事实定级

### Requirement: MCP 工具默认免审批，approval_rules 显式声明需审批操作

对 MCP 工具（运行时全名形如 `{server}__{tool}`），`risk_for` MUST 默认返回 `none`（免审批），除非命中该 agent 配置的 `approval_rules`。系统 SHALL 支持 agent.yaml `mcp_servers[].approval_rules: [{tool, when?}]`：`tool` 匹配该 server 内本地工具名；`when` 为 `参数名 → 允许值列表` 的 map，调用参数值命中列表其一则该参数匹配，多个参数 MUST 全部匹配（AND）；省略 `when` MUST 视为整工具匹配。命中规则 → `medium`；未命中或该 server 未配置 `approval_rules` → `none`。该默认姿态（未声明即免审批）MUST 在文档显著标注：新挂 MCP server 若不配规则，其危险操作免审批直跑，安全责任在 agent owner 显式声明。

#### Scenario: 按参数命中升审批

- **WHEN** agent 调用 `google-workspace__manage_email`，参数 `operation="send"`，且 approval_rules 含 `{tool: manage_email, when: {operation: [send, reply, replyAll, forward]}}`
- **THEN** `risk_for` 返回 `medium`

#### Scenario: 同工具读操作免审批

- **WHEN** 同上配置下，agent 调用 `manage_email` 参数 `operation="read"`
- **THEN** 未命中 `when` → `risk_for` 返回 `none`，免审批

#### Scenario: 整工具规则无 when

- **WHEN** approval_rules 含 `{tool: some_tool}`（无 `when`），agent 以任意参数调用 `srv__some_tool`
- **THEN** `risk_for` 返回 `medium`

#### Scenario: 未配置 server 免审批

- **WHEN** 某 MCP server 未声明 `approval_rules`，agent 调用其任一工具
- **THEN** `risk_for` 返回 `none`

### Requirement: 内置 google-workspace 发件默认审批规则

系统 SHALL 为 `google-workspace` server 随附开箱默认规则：`manage_email` 的 `operation ∈ {send, reply, replyAll, forward}` MUST 默认定级 `medium`，使发邮件默认走审批，关闭 MCP 零审批漏洞。该默认 MUST 可被 agent.yaml 显式配置覆盖。

#### Scenario: 未配置时发邮件仍审批

- **WHEN** agent 挂载 `google-workspace` 但 agent.yaml 未写该 server 的 approval_rules，agent 调用 `manage_email` 参数 `operation="send"`
- **THEN** 命中内置默认规则，`risk_for` 返回 `medium`

#### Scenario: 未配置时读邮件免审批

- **WHEN** 同上，agent 调用 `manage_email` 参数 `operation="search"`
- **THEN** 不命中发件默认规则，`risk_for` 返回 `none`

