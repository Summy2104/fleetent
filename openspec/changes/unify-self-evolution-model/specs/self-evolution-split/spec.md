## MODIFIED Requirements

### Requirement: 审批渠道按 proposal 类型路由

审批门 SHALL 按 proposal 类型解析**审批人**(由影响范围决定找谁):user memory → 该 memory 的 **owner**(该 user 本人,owner 同意对自己记忆的改动);shared memory / skill / KB → agent 归属 **team / tenant 负责人**(admin)。但**触达渠道统一为 agent-owned 外呼**——经 `agent_config.resolve_approvers`(读 agent.yaml `ApprovalRouting`)解析审批人地址 + im_gateway **DM**(+ Slack 按钮 / 文本命令)触达,全在 agent 侧、**default-closed**(找不到审批人不自动 apply)。审批动作 MUST NOT 经 platform console;platform console SHALL 仅作**只读投影**(查看提案 / 审批历史),不是审批渠道。(本要求由 R1 `agent-owned-approval` / `approval-suspend-resume` 统一为 agent 侧外呼,取代原 skill/KB 经 platform console 审的旧路由。)

#### Scenario: 个人记忆找 owner、agent 侧外呼
- **WHEN** 门处理 user memory proposal
- **THEN** 它 SHALL 经 agent-owned 外呼 DM 推送给该 memory 的 owner(该 user 本人)
- **AND** 该路由 SHALL NOT 依赖 platform

#### Scenario: skill/KB 找 team/tenant 负责人、经 DM 非 console
- **WHEN** 门处理 skill 或 KB proposal
- **THEN** 它 SHALL 经 `resolve_approvers` 解析 agent 归属 team / tenant 负责人(admin)并经 im_gateway DM 触达
- **AND** 审批动作 SHALL NOT 经 platform console(console 仅供只读查看)

#### Scenario: 无审批人 default-closed
- **WHEN** 任一类型 proposal 解析不到可达审批人
- **THEN** 提案保持 pending、不自动 apply,不回退到 platform console
