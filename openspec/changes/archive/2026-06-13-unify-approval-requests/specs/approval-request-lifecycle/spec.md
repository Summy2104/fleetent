# approval-request-lifecycle Delta

## ADDED Requirements

### Requirement: 统一审批请求作单一生命周期真相源
系统 SHALL 用一张 `approval_requests` 表（agent 侧 `agent_state.db`，嵌入式 Y）作所有人在环审批的**生命周期单一真相源**，覆盖工具门与反思提案两类。该表 SHALL 含：`id` · `subject_type`（`tool_call` / `memory_proposal` / `skill_proposal`）· `subject_id`（多态主体引用，约定引用、无 DB 外键）· `requester_user_id` · `risk` · `status`（`pending`→`approved`/`rejected`/`expired`）· `approver_user_id` · `decided_at` · `reason` · `routing_key`（找审批人用，工具门为 tool_name、提案为 `reflection_{domain}_proposal` 合成名）· `created_at` · `expires_at`。审批生命周期状态 MUST NOT 再在 `approvals`（已退役）或 `reflection_proposals`（仅留实体+apply 列）等其它表重复建模。

#### Scenario: 两类审批共用一张表
- **WHEN** 工具门触发一次审批、或反思生成一条 memory/skill 提案
- **THEN** 各写入一行 `approval_requests`，以 `subject_type` 区分，`subject_id` 指向各自主体（工具门的恢复上下文在 session meta；提案实体在 `reflection_proposals`）

#### Scenario: 审批生命周期单一真相源
- **WHEN** 查询某审批的 status / 审批人 / 决定时间 / 过期
- **THEN** 这些字段只从 `approval_requests` 读取，不存在第二张表并行维护同一生命周期

### Requirement: 统一审批路由按主体类型分派 resolve
系统 SHALL 提供单一审批路由：通知（经 `resolve_approvers` + im_gateway outbound DM 找审批人，工具门与提案共用）→ 审批人 IM 回复 → 按 `approval_requests.subject_type` 分派 resolve。`tool_call` SHALL 分派到恢复挂起 run 的处理（permission-gate 逻辑）；`memory_proposal` / `skill_proposal` SHALL 分派到 approve+apply 的处理（reflection apply 逻辑）。MUST NOT 存在两个平行的 resolve 入口（收敛此前 permission_gate 与 reflection 各一套的 resolve）。

#### Scenario: 工具门审批回复恢复 run
- **WHEN** 审批人对一条 `subject_type=tool_call` 的请求回复 approve
- **THEN** 统一路由分派到恢复挂起 run 的处理，被门控的工具调用继续执行

#### Scenario: 提案审批回复触发 apply
- **WHEN** 审批人对一条 `subject_type=memory_proposal` 或 `skill_proposal` 的请求回复 approve
- **THEN** 统一路由分派到 approve+apply 处理，提案被 apply（memory 写记忆 / skill 写 bundle）；reflection 的审批闭环不再悬空

#### Scenario: 拒绝按类型一致处理
- **WHEN** 审批人对任一 `subject_type` 回复 reject
- **THEN** `approval_requests.status` 置 `rejected` 并记 `reason`，不执行该审批的后续动作（run 不恢复 / 提案不 apply）

### Requirement: 统一过期与待审查询
`approval_requests` 的 `pending` 行 SHALL 按 `expires_at` 统一过期：超时由 reconcile 例程置 `status=expired` 并清理对应主体侧的待恢复状态（工具门的 session meta pending 项）。系统 SHALL 支持一次查询跨 `subject_type` 列出 pending 审批（统一待审收件箱），可按 `subject_type` 筛。

#### Scenario: 过期统一 reconcile
- **WHEN** 一条 pending `approval_requests` 超过 `expires_at`，reconcile 例程运行
- **THEN** 该行 `status=expired`；若为 tool_call，其 session meta 的 pending 项一并清理，会话保持一致

#### Scenario: 统一待审收件箱
- **WHEN** 列出当前 pending 审批
- **THEN** 一次查询返回跨 tool_call / memory_proposal / skill_proposal 的 pending 行，按 `subject_type` 可筛
