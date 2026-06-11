## MODIFIED Requirements

### Requirement: 非凭证身份获取路径

系统 SHALL 支持三条非凭证身份路径：② **继承**——sub-agent / 回合内内部调用沿用父/会话已解析的 `Principal`，不重认；③ **存档复检（按域）**——cron 从 `scheduled_tasks.user_id` load 后，复检 MUST 在该身份**所属的域**内执行：`user_id` 为平台用户（`users` 表中存在）→ 复检状态，已 block / 删 / 移出主体则拒；任务带 IM origin 的**渠道担保身份**（不在 `users` 表中，由 IM edge 准入）→ MUST NOT 经 `user_store` 复检，凭存档身份放行执行；既无平台用户记录、又无 IM origin → 拒。部署中不存在用户管理（`users` 表缺失）时 MUST 信任存档身份放行（agent 独立运行基线）；`user_id` 为 `default` 占位时放行；④ **纯基础设施**——无人类 owner 的任务用显式 `system` 标识，MUST NOT 冒充 user，审计如实记 `system`。**继承 MUST 沿用父/会话 Principal 的完整字段（含 `tenant_id`），MUST NOT 用写死的 `tenant_id`（如 `"default"`）覆盖继承来的主体。**

#### Scenario: sub-agent 继承
- **WHEN** 核派生 sub-agent 或做回合内内部调用
- **THEN** 沿用父/会话的 `Principal`，不重新认证

#### Scenario: sub-agent 继承父主体（不写死 default）
- **WHEN** 主体 `T1` 的运行派生 sub-agent，父 `Principal.tenant_id` 为 `T1`
- **THEN** sub-agent 的 `Principal.tenant_id` 为 `T1`，不被写死为 `"default"`

#### Scenario: 工具内派生 agent 透传 Principal
- **WHEN** 经 `invoke_agent` 类工具在回合内调起另一 agent
- **THEN** 被调 agent run 收到当前回合的 `Principal`（含其 `tenant_id`），而非 principal-less 调用

#### Scenario: cron 存档复检（平台用户）
- **WHEN** 定时任务触发，`scheduled_tasks.user_id` 是 `users` 表中的平台用户且状态为 blocked
- **THEN** 拒绝执行

#### Scenario: cron 存档复检（IM 渠道担保身份）
- **WHEN** 定时任务触发，`user_id` 不在 `users` 表中，但任务的 `origin` 带 IM 平台来源
- **THEN** 视为渠道担保身份，不经 `user_store` 复检，按存档 `user_id` 构造 Principal 执行

#### Scenario: cron 存档复检（未知非 IM 身份）
- **WHEN** 定时任务触发，`user_id` 不在 `users` 表中且任务无 IM origin
- **THEN** 拒绝执行（平台域"已删用户的任务不再执行"语义）

#### Scenario: 无用户管理部署放行
- **WHEN** 定时任务在 `users` 表不存在的 standalone 部署中触发
- **THEN** 信任存档身份构造 Principal 执行，不因缺少平台用户管理而拒绝

#### Scenario: 基础设施用 system 标识
- **WHEN** 无 owner 的基础设施任务（如 TTL 清理）运行
- **THEN** 以显式 `system` 标识运行、不构造冒充某 user 的 Principal，审计记 `system`
