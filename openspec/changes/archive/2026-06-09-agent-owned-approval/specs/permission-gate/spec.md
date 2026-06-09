## ADDED Requirements

### Requirement: 主动联系审批人（请求者 ≠ 审批人）
撞到门时，系统 **MUST** 从 agent 的 `approval` 路由配置（见 `permission-gate-config`）解析出审批人，并经 **agent 主动发起的出站 DM**（见 `im-outbound-messaging`）把审批请求投递给他们，与触发该工具的会话无关。请求者 **MUST** 被告知"审批进行中"。审批回执 **MUST** 按 `approval_id` 关联到挂起的请求，无论它从哪个会话/线程到达。

#### Scenario: 审批人与请求者不同
- **WHEN** 高风险工具由请求者 R 触发，而 `approval` 配置路由到审批人 A（A ≠ R）
- **THEN** agent 经出站 DM 把审批请求发给 A，并通知 R "等待审批"

#### Scenario: 回执跨会话按 approval_id 关联
- **WHEN** 审批人 A 在 A 自己的 DM 线程（而非 R 的会话）里处理该请求
- **THEN** 门把该回执匹配到挂起的 `approval_id`，并放行原工具调用

### Requirement: 审批状态由 agent 自持、独立于 platform
permission gate **MUST** 经 agent 自持的 store 边界持久化审批请求与状态，且**不得** `import fleetent.user_store` 或任何 `fleetent.platform.*`。当 platform/管理库不存在时（单机 `fleetent agent run`），审批 **MUST** 仍能工作。

#### Scenario: 无 platform 库的单机审批
- **WHEN** 单机 agent（无 platform、管理库不存在）触发门并由审批人处理
- **THEN** 审批被创建、投递、处理，全程不经任何 platform 模块或管理表

#### Scenario: permission_gate 无 platform import
- **WHEN** 导入 `governance.permission_gate` 模块
- **THEN** 它既不 `import fleetent.user_store` 也不 `import fleetent.platform.*`（由依赖护栏强制）

### Requirement: 审批人记为不透明 actor 标签
解析出的审批人 **MUST** 存为不透明字符串，绝不作为指向 platform `users` 表的外键，使 agent 不持有 platform 身份。

#### Scenario: 处理时存不透明 actor
- **WHEN** 一个审批由审批人标识 X 处理
- **THEN** 存储的审批人值逐字等于 X，不对 `users` 表做 join 或校验

## MODIFIED Requirements

### Requirement: Risk-level declaration
Tools SHALL declare their risk level at registration time via `@tool(risk_level=...)`.

#### Scenario: Tool with no risk
- **WHEN** a tool is registered with `risk_level="none"` (or no risk_level specified)
- **THEN** it executes immediately after access control passes

#### Scenario: Tool with medium risk
- **WHEN** 注册了 `risk_level="medium"` 的工具被调用
- **THEN** 经出站 DM 把审批请求投递给从 `approval` 配置中为 `medium`（或其 `by_tool` 覆盖）解析出的审批人，在执行前完成；若解析不到审批人，按 `on_no_approver`（default-closed）拒绝，**不回落"请求者本人确认"**

#### Scenario: Tool with high risk
- **WHEN** 注册了 `risk_level="high"` 的工具被调用
- **THEN** 经出站 DM 把审批请求投递给从 `approval` 配置中为 `high`（或其 `by_tool` 覆盖）解析出的审批人，并通知请求者"等待审批"

### Requirement: Approval persistence
所有审批请求与结果 **MUST** 记录到 **agent 侧审批 store**，其 schema 仅由 agent 运行时拥有（**不再**同时由 Alembic 定义——`approvals` 表此前的双权威被移除）。每条记录 **MUST** 带上发起的 `session_id`。

#### Scenario: Approval record lifecycle
- **WHEN** 一个 permission gate 触发
- **THEN** 在 agent 侧 store 插入一条 `status=pending` 记录，处理后更新为 `approved`/`rejected`/`timeout`

#### Scenario: 记录带上发起的 session
- **WHEN** 为会话 S 中的某次工具调用创建审批
- **THEN** 存储记录的 `session_id` 等于 S（而非空字符串）

#### Scenario: 单一 schema 权威
- **WHEN** 创建 agent 侧审批 store 的 schema
- **THEN** 仅由 agent 侧 store 边界创建，`approvals` 表不再由任何 Alembic 迁移（重）定义
