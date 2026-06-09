## ADDED Requirements

### Requirement: agent.yaml 必须暴露 `approval` 审批人路由块
`AgentFile` **MUST** 支持一个 `approval` 配置块，主轴为 `by_risk`（`medium`/`high`），并支持 `by_tool` 按工具名覆盖（`by_tool` 优先于 `by_risk`）。每个条目声明 `approvers`（一组内部 user_id）、`policy`（`any` 或 `all`）。审批人 user_id **MUST** 经 im-user-mapping 解析为可触达的 IM 地址。

#### Scenario: 按风险等级路由
- **WHEN** `approval.by_risk.high.approvers = [u_lead]` 且某 high 风险工具被触发
- **THEN** 审批请求被路由给 `u_lead`（经 im-user-mapping 解析为其 IM 地址）

#### Scenario: 按工具覆盖
- **WHEN** `approval.by_tool.delete_prod_db.approvers = [u_ops]` 且 `delete_prod_db`（high）被触发
- **THEN** 审批人取 `by_tool` 的 `u_ops`，覆盖 `by_risk.high`

### Requirement: 多审批人策略 any/all
当一个条目配置多个 `approvers` 时，`policy` **MUST** 决定通过条件：`any` = 任一审批人通过即放行；`all` = 全部通过才放行（任一拒绝即拒）。

#### Scenario: any 策略，首个响应即决
- **WHEN** `policy: any`、approvers = [A, B]，A 先 approve
- **THEN** 工具调用放行，不再等待 B

#### Scenario: all 策略，需全部通过
- **WHEN** `policy: all`、approvers = [A, B]，仅 A approve
- **THEN** 工具调用仍阻塞，直到 B 也 approve；若 B reject 则整体拒绝

### Requirement: 兜底 default-closed
`approval` 块 **MUST** 支持 `on_no_approver` 兜底，默认 `reject`。在以下任一情况下，审批 **MUST** 按 default-closed 拒绝：未为该风险/工具配置审批人、向审批人 DM 发送失败、超时未响应。

#### Scenario: 未配置审批人
- **WHEN** 某 high 风险工具触发，但 `approval` 未为其解析出任何审批人
- **THEN** 审批按 `on_no_approver: reject` 直接拒绝（不放行）

#### Scenario: DM 发送失败
- **WHEN** 审批人不可达导致出站 DM 发送失败
- **THEN** 审批被拒绝（default-closed），不静默放行

### Requirement: `approval` 块取代连接器级 require_approval
新的 `approval` 路由块 **MUST** 取代连接器级 `ConnectorAccess.require_approval` 布尔开关作为审批控制面；是否设门统一由 agent 的审批配置决定。

#### Scenario: 由 approval 配置决定设门
- **WHEN** agent 配置了 `approval` 路由块
- **THEN** 审批是否触发、路由给谁，由该块决定，而非由连接器级 `require_approval`
