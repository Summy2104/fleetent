## Context

审批门（permission gate）的"哪些操作需要审批"目前由散落在 `tools/builtin_tools.py` 各 `@tool(risk_level=…)` 装饰器、`integrations/mcp` 注册逻辑、以及 `governance/permission_gate` 的隐含默认共同决定，没有统一原则：

- `run_code`/`send_im_message`/`invoke_agent` 静态 `medium`，`send_file` 用 callable `_send_file_risk`（D6/D7），其余 `low`/`none`。
- **MCP 工具注册时不带 risk → 默认 `none` → 完全不过门**。my-bot 挂着 google-workspace MCP，意味着 agent 可零审批发邮件、删 Drive。
- `runtime/loop.py` dispatch 处 `get_risk_level` / `evaluate_risk_level` 取风险，再经 `resolve_action_mode`（action-gate）映射 DIRECT/SANDBOX/APPROVAL/REJECT。

经与产品（张洋）逐项确认，审批面应收窄到**唯一原则**：审批 ⟺ agent 主动把内容投递给「当前对话发起人以外的接收方」。约束：`governance` 不得反向 `import platform`；`run_code` 的封闭性 fail-closed（`sandbox-containment-gating`）不可被覆盖。

## Goals / Non-Goals

**Goals:**
- 单一、可解释的审批原则（接收方身份轴），固化进代码而非散落。
- 一个中心裁决入口 `governance/approval_policy.risk_for(tool_name, args, tool_context)`，作为 action-gate 的唯一风险来源。
- 关闭 MCP 零审批漏洞：默认免审批 + agent.yaml `approval_rules` 显式声明需审批的 MCP 操作（含按参数匹配，区分 manage_email 的读 vs 发）。
- `send_im_message` 按接收方动态定级、`send_file` 恒免审批、`invoke_agent` 免审批。

**Non-Goals:**
- 不改 `run_code` 的审批：其免审批由 `sandbox-containment-gating` 治理（封闭→免、无封闭→升审批），覆盖它会在无沙箱环境制造"主机任意执行零审批"漏洞。
- 不改 action-gate 的 risk→mode 映射（none/low→DIRECT、medium→APPROVAL 默认）；本变更只改"风险如何被定级"，不改"定级后如何处置"。
- 不做频道审批投递机制（按钮真人可用）。
- 不修 run_code 审批后挂起 bug（独立问题）。

## Decisions

### D1：判定轴 = 接收方身份，而非动作类型
审批 ⟺ 主动投递给「当前对话地址以外的接收方」。当前对话地址 = `tool_context.session_context` 派生的 `(chat_type, channel/dm 用户, 频道)`。回当前对话（同一 DM 用户或同一频道）免审批；指向他人/他群才审批。
- **为何**：这是 send_file D6 已验证的逻辑，推广为通用原则后内置工具用同一把尺子，可解释、可预测。
- **备选**：按"不可逆副作用"（更宽，会把删 Drive 等也纳入，与产品"其余不审批"取向相悖）；按"数据出内网"（与数据主权对齐但粒度过粗）。均被否。

### D2：中心裁决入口 `approval_policy.risk_for`
新建 `governance/approval_policy.py`，唯一函数 `risk_for(tool_name, args, tool_context) -> "none"|"low"|"medium"|"high"`。内置工具的接收方判定、MCP 的 approval_rules 匹配都在此裁决。`registry.evaluate_risk_level` 与 `loop.py` dispatch 委托它。
- **为何**：终结散落；风险定级集中一处便于审计与测试。
- **与现状衔接**：`@tool(risk_level=…)` 仍可声明静态档作为兜底/默认；`approval_policy` 对需要动态判定的工具（send_im_message、MCP）给出最终档。保留"风险定级只来自服务端（反逃逸）"——LLM 的 tool_args 永不降档。

### D3：send_im_message 动态、send_file 静态
- `send_im_message(target, target_type, …)`：`risk_for` 比较 `(target, target_type)` 与当前对话地址；相同→`none`（回当前对话），不同→`medium`。无法解析当前对话地址时 fail-closed 到 `medium`。
- `send_file(path)`：无接收方参数，恒回当前对话 → 恒免审批。删除 callable `_send_file_risk`。
- **跨 scope 护栏（正交保留）**：send_file 解析 `/exchange` 跨 scope 工件 → **硬拒绝**（数据隔离，非审批；send_file 已无审批逃生口）。send_im_message 的 files 跨 scope 仍由"已审批=跨 scope 授权"放行（不变）。

### D4：MCP 默认免审批 + agent.yaml approval_rules
agent.yaml `mcp_servers[].approval_rules: [{tool, when?}]`。匹配：运行时全名 `{server}__{tool}`；`when` 为 `参数名→允许值列表` 的 map，调用参数命中即匹配，多参数 AND，省略 `when`=整工具。命中→`medium`，未命中/未配置→免审批。`integrations/mcp` 注册时把规则交给 `approval_policy`；`risk_for` 对 `{server}__*` 名查规则表。
- **默认姿态**：未配置的 MCP 操作免审批（产品取向：窄审批面，安全责任在 agent owner 显式声明）。设计明记该取舍：新挂 MCP server 若不配规则，其危险操作免审批直跑。
- **内置默认规则**：`google-workspace` 的 `manage_email`（`operation ∈ {send, reply, replyAll, forward}`）随附为开箱默认。

### D5：invoke_agent 免审批
`agent-invocation` 去掉前置 `medium` 门。被调子 agent 在其自身运行中产生的外发动作仍各自经 `approval_policy` 受门，故父层不重复门。

## Risks / Trade-offs

- [收窄审批面后，MCP 危险写操作（删 Drive/改日历等）默认免审批] → 这是产品明确取向（接收方身份轴，只门"发给他人"）；缓解=文档显著标注 + 提供 approval_rules 让 owner 按需加门 + 内置 email 默认规则示范。
- [send_im_message 动态定级误判"当前对话地址"导致漏门] → fail-closed：无法解析地址或解析不确定时返回 `medium`（宁可多一次审批）。
- [send_file 去掉审批逃生口后，跨 scope 工件硬拒绝可能挡住合理场景] → 合理跨 scope 投递改走 send_im_message（带 files、经审批）；send_file 仅服务"回当前对话本 scope 文件"。
- [risk_for 成为单点] → 纯函数、无 IO、全单测覆盖；异常 fail-closed 到 `medium`（沿用现有 `evaluate_risk_level` 语义）。
- [与正在重构的 IM 访问模型（im 命名空间 S2/S3）潜在耦合] → 本变更只读 `session_context` 的 chat_type/对话地址（稳定语义），配置落 `mcp_servers`（不碰 `im` 命名空间），正交。
