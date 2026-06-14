## Why

工具风险分级散落在各处（每个 `@tool(risk_level=…)` 装饰器各写各的），审批边界因此不一致且有漏洞：沙箱内的 `run_code` 弹审批，而 **MCP 工具注册时风险默认 `none`、完全不过审批门**——agent 可零审批地发邮件、删 Drive 文件。本变更确立**单一审批原则**、把审批面收窄到真正需要的外发动作、并关闭 MCP 零审批漏洞。

## What Changes

- **确立单一审批原则（接收方身份轴）**：审批 ⟺ agent **主动把内容投递给「当前对话发起人以外的接收方」**（给别人发私信 / 私发文件 / 发邮件）；回当前对话本人/本频道、本地与沙箱内操作一律免审批。
- **新建中心裁决入口** `governance/approval_policy.risk_for(tool_name, args, tool_context)`；`runtime/loop.py` dispatch 与 `tools/registry.evaluate_risk_level` 委托它，终结散落。
- **`send_im_message`**：由恒 `medium` 改为**按接收方动态定级**——目标解析 == 当前对话地址（同一 DM 用户 / 同一频道）→ 免审批；指向他人 / 他群 → `medium`。**BREAKING**（外发行为变更）。
- **`send_file`**：由 D6/D7 callable 风险改为**恒免审批**（无接收方参数，永远回当前对话——DM 或当前频道）。`/exchange` 跨 scope 工件经 send_file 改为**硬拒绝**（send_file 不再有审批逃生口；跨 scope 投递唯一合法路径=已审批的 `send_im_message` files）。
- **`invoke_agent`**：由 `medium` 改为免审批（非"外发给人"；被调子 agent 自身的外发动作仍各自过门）。
- **MCP 工具**：默认免审批；新增 agent.yaml `mcp_servers[].approval_rules`（按 `tool` 名 + 可选 `when` 参数条件匹配）命中 → `medium`；省略 `when` = 整工具审批；内置 `google-workspace` 的 `manage_email`（`operation ∈ {send, reply, replyAll, forward}`）默认规则。关闭 MCP 零审批漏洞。
- **不在范围 — `run_code`**：维持现状。其免审批由既有 `sandbox-containment-gating` 治理（沙箱封闭 → 免审批；无封闭 → fail-closed 升审批）。**MUST NOT** 用本审批策略覆盖，否则无沙箱环境会出现"主机任意代码执行零审批"漏洞。（用户遇到的 run_code 审批弹窗实为该 agent 运行时 sandbox 未封闭，属配置/运维。）
- **不在范围 — 频道审批投递机制**：经验证频道审批按钮真人点击可用，真实用户无阻塞；频道打字审批 / 线程入站作为可选未来增强，本次不做。

## Capabilities

### New Capabilities
- `approval-policy`: 单一审批原则（接收方身份轴）的中心裁决入口 `risk_for(tool_name, args, tool_context)`，与 MCP `approval_rules` 配置语义；作为所有工具风险定级的**权威来源**，结果喂给既有 `action-gate` 映射为处置 mode。MCP 默认免审批 + 规则命中升 medium 的取舍亦在此声明。

### Modified Capabilities
- `builtin-outbound-tool`: `send_im_message` 由"恒 medium、外发恒人工门"改为"按接收方身份"——回当前对话免审批、发给他人/他群 medium。
- `file-exchange`: `send_file` 由 D6/D7 callable 风险改为恒免审批；跨 scope 工件在 send_file 由"升级审批"改为"硬拒绝"（去掉审批逃生口），保留 send_im_message files 的已审批跨 scope 路径不变。
- `agent-invocation`: `invoke_agent` 由 `risk_level="medium"` 改为免审批（不再前置审批门；子 agent 内部动作仍各自受门）。

## Impact

- **owning package**：`governance`（新增 `approval_policy.py`）。
- **public API surface**：`approval_policy.risk_for(tool_name: str, args: dict, tool_context) -> str`（唯一裁决入口，返回 none/low/medium/high）。
- **consumers**：`runtime/loop.py`（dispatch 委托）、`tools/registry`（`evaluate_risk_level` 委托）、`tools/builtin_tools`（send_im_message 改动态、send_file 改静态免审批）、`integrations/mcp/client.py`（注册时载入 agent 的 approval_rules）、`agent_config`（解析 `mcp_servers[].approval_rules`）。
- **owned tables**：无（不新增/变更持久化）。
- **config namespace**：新增 agent.yaml `mcp_servers[].approval_rules`。
- **cross-module dependencies**：`governance.approval_policy` 读 `tool_context.session_context`（当前对话地址）判接收方身份；**MUST NOT** `import fleetent.platform.*`。
- **migration / shim plan**：`send_file` 的 `risk_level` 由 callable `_send_file_risk` 改为静态免审批（删除该 callable）；`send_im_message` 由静态 `medium` 改为 callable；无数据迁移；`/exchange` 跨 scope 归属硬护栏保留（仅去掉 send_file 的审批豁免分支）。
