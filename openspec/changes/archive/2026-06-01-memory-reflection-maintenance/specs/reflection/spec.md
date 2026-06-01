## ADDED Requirements

### Requirement: User Memory maintenance proposal lifecycle
reflection SHALL provide a proposal lifecycle for User Memory maintenance actions without directly mutating memory by default.

#### Scenario: Proposal is created as pending
- **WHEN** reflection 发现 User Memory maintenance candidate
- **THEN** 系统创建 status=`pending` 的 proposal
- **AND** 不创建、更新或删除 `memory_items`

#### Scenario: Proposal can be approved
- **WHEN** proposal owner 确认 pending proposal
- **THEN** proposal status 变为 `approved`

#### Scenario: Proposal can be rejected
- **WHEN** proposal owner 拒绝 pending proposal
- **THEN** proposal status 变为 `rejected`

#### Scenario: Applied proposal is recorded
- **WHEN** approved proposal 成功应用到 User Memory
- **THEN** proposal status 变为 `applied`

#### Scenario: Expired proposal cannot be applied
- **WHEN** proposal status 为 `expired`
- **THEN** 系统拒绝应用该 proposal

### Requirement: User Memory owner approval
User Memory maintenance proposal SHALL be owned by the target `user_id`, and memory-changing actions require owner approval unless an explicit low-risk auto-maintenance policy allows the action.

#### Scenario: Proposal has user owner
- **WHEN** reflection 创建 User Memory maintenance proposal
- **THEN** proposal 包含目标 `user_id`
- **AND** 该 `user_id` 是默认确认主体

#### Scenario: Unapproved proposal does not mutate memory
- **WHEN** proposal status 为 `pending`
- **AND** 不存在适用的低风险自动维护策略
- **THEN** apply 操作不修改 User Memory

#### Scenario: Admin is not default owner
- **WHEN** proposal 目标是 User Memory
- **THEN** 系统不允许管理员或 operator 默认替用户确认内容修改

#### Scenario: High-risk action requires owner approval
- **WHEN** proposal action 是 high-risk
- **THEN** 系统必须要求 owner approval
- **AND** 低风险自动维护策略不能执行该 action

### Requirement: Memory maintenance action risk boundaries
reflection SHALL classify User Memory maintenance proposals by risk before apply.

#### Scenario: Merge rewrite and compact require approval by default
- **WHEN** proposal action 是 `merge`、`rewrite` 或 `compact`
- **THEN** proposal 默认为需要 owner approval

#### Scenario: Delete always requires owner approval
- **WHEN** proposal action 是 `delete`
- **THEN** proposal 被标记为 high-risk
- **AND** 系统没有 owner approval 不得执行删除

#### Scenario: Low-risk auto policy is narrow
- **WHEN** 用户显式开启低风险自动维护策略
- **THEN** 系统只允许 low-risk proposal 自动 apply
- **AND** 不允许自动执行 delete、跨用户动作或低置信度冲突处理

### Requirement: Interaction-time confirmation metadata
reflection SHALL mark proposals that are safe to present as lightweight confirmation during a related user interaction.

#### Scenario: Current conversation creates lightweight confirmation candidate
- **WHEN** 当前对话明确修正了用户身份、偏好或当前状态
- **THEN** reflection 可以生成适合交互中轻量确认的 proposal metadata
- **AND** 该 proposal 在用户确认前不修改 User Memory

#### Scenario: Bulk review remains available
- **WHEN** 用户主动请求整理记忆
- **THEN** 系统可以按 user_id 查询 pending maintenance proposals

### Requirement: Shared Memory and KB migration suggestions
reflection SHALL NOT write team、tenant、project or customer shared context into User Memory.

#### Scenario: Shared context candidate is not written to User Memory
- **WHEN** reflection 发现候选内容更像团队共识、项目惯例、客户背景或组织运行经验
- **THEN** 系统创建 `suggest_shared_memory_or_kb` proposal
- **AND** 不创建、更新或删除 User Memory

#### Scenario: Shared Memory is not implemented by this change
- **WHEN** `suggest_shared_memory_or_kb` proposal 被创建
- **THEN** 系统不创建 Shared Memory item
- **AND** 系统不把 team 或 tenant 内容写入 `memory_items.user_id`

### Requirement: Maintenance apply uses Memory public API
reflection SHALL apply approved User Memory proposals through memory-layer public API instead of direct SQL.

#### Scenario: Apply does not write memory table directly
- **WHEN** approved proposal 被应用
- **THEN** reflection 调用 memory-layer public API 修改 User Memory
- **AND** reflection 不直接写 `memory_items` 表
