## MODIFIED Requirements

### Requirement: 统一审批路由按主体类型分派 resolve
系统 SHALL 提供单一审批路由：通知（经 `resolve_approvers` + im_gateway outbound DM 找审批人，工具门与提案共用）→ 审批人 IM 回复 → 按 `approval_requests.subject_type` 分派 resolve。`tool_call` SHALL 分派到恢复挂起 run 的处理（permission-gate 逻辑）；`memory_proposal` / `skill_proposal` SHALL 分派到 approve+apply 的处理（reflection apply 逻辑）。MUST NOT 存在两个平行的 resolve 入口（收敛此前 permission_gate 与 reflection 各一套的 resolve）。

resolve 的 HTTP 入口 SHALL 仅存在于 agent 侧（`agent_app` 的 resolve 端点）。platform 控制面 MUST NOT 暴露 resolve 端点——platform 对审批保持只读投影（list / get），审批的实际 resolve 由 agent 侧拥有。

reflection 提案的 approver 路由 SHALL 按**域 + 目标**细分 routing key：`skill` 提案用 `reflection_skill_proposal`；`memory` 域的 shared 建议（`action=suggest_shared_memory_or_kb`）用 `reflection_shared_memory_proposal`；`memory` 域的 user-memory 维护用 `reflection_user_memory_proposal`。同一提案在通知与台账两处 SHALL 使用同一 routing key。

#### Scenario: 工具门审批回复恢复 run
- **WHEN** 审批人对一条 `subject_type=tool_call` 的请求回复 approve
- **THEN** 统一路由分派到恢复挂起 run 的处理，被门控的工具调用继续执行

#### Scenario: 提案审批回复触发 apply
- **WHEN** 审批人对一条 `subject_type=memory_proposal` 或 `skill_proposal` 的请求回复 approve
- **THEN** 统一路由分派到 approve+apply 处理，提案被 apply（memory 写记忆 / skill 写 bundle）；reflection 的审批闭环不再悬空

#### Scenario: 拒绝按类型一致处理
- **WHEN** 审批人对任一 `subject_type` 回复 reject
- **THEN** `approval_requests.status` 置 `rejected` 并记 `reason`，不执行该审批的后续动作（run 不恢复 / 提案不 apply）

#### Scenario: platform 不暴露 resolve 入口
- **WHEN** 检视 platform 控制面 HTTP 表面
- **THEN** 不存在 resolve 审批的端点；platform 仅提供审批的只读列表/查询，resolve 只能经 agent 侧端点

#### Scenario: user-memory 与 shared 提案路由到不同 approver
- **WHEN** reflection 在 memory 域生成一条 user-memory 维护提案和一条 `suggest_shared_memory_or_kb` 提案
- **THEN** 前者用 routing key `reflection_user_memory_proposal`、后者用 `reflection_shared_memory_proposal`，二者按 agent 配置可解析到不同 approver
