# agent-im-access Specification

## Purpose
TBD - created by archiving change add-agent-im-access. Update Purpose after archive.
## Requirements
### Requirement: Agent IM 能力声明
每个 agent SHALL 在 `agents` 表声明两个布尔能力位 `supports_dm` 与 `supports_groups`，表示该 agent 是否支持私聊 / 群聊。两者 SHALL 默认 `0`（关闭）。能力是 **agent 级、非版本化**的策略立场（不随 `agent_versions` 快照）。本阶段只立存储与默认；运行时按能力分流准入由 IM 访问模型阶段 3 落地。

#### Scenario: 新建 agent 能力默认全关
- **WHEN** 创建一个新 agent
- **THEN** 其 `supports_dm` 与 `supports_groups` 均为 `0`

#### Scenario: admin 开启群聊能力
- **WHEN** admin 把某 agent 的 `supports_groups` 设为开
- **THEN** `agents.supports_groups` 为 `1`，`supports_dm` 不受影响

### Requirement: Agent 群白名单存储
系统 SHALL 提供 `agent_im_groups` 表存储"某 agent 的 bot 准许在哪些群交互"，键为 `(agent_id, platform, group_id)`。`agent_id` SHALL 为 INTEGER 且声明 FK→`agents.id` ON DELETE CASCADE（agent 删除级联清理）。无行 SHALL 表示该 agent 在该平台不进任何群（默认关，安全默认）。群 id 为平台特定值（Slack channel / Telegram chat）。本阶段只立存储；运行时群准入强制由阶段 3 落地。

#### Scenario: 绑定一个群到 agent
- **WHEN** admin 为某 agent 在 `slack` 平台绑定群 `C0123`
- **THEN** `agent_im_groups` 出现一行 `(agent_id, "slack", "C0123", ...)`

#### Scenario: 删除 agent 级联清理群白名单
- **WHEN** 一个持有 `agent_im_groups` 行的 agent 被删除
- **THEN** 该 agent 的 `agent_im_groups` 行随 FK ON DELETE CASCADE 一并删除

#### Scenario: 默认无群
- **WHEN** 某 agent 从未绑定任何群
- **THEN** `agent_im_groups` 中该 agent 无行（阶段 3 闸据此默认不进任何群）

### Requirement: Admin 配置 IM 能力与群白名单
系统 SHALL 暴露 admin 端点配置 agent 的 IM 能力（`supports_dm`/`supports_groups`）与群白名单（绑定/解绑 `(platform, group_id)`），要求 `admin`/`built_in_admin`。用户准入沿用既有 `user_agents` 的 user 绑定端点（不在本能力新增）。配置经 store 边界写入、named parameters。

#### Scenario: 配置群白名单经审计与角色门
- **WHEN** 一个 `admin` 绑定/解绑某 agent 的 IM 群
- **THEN** `agent_im_groups` 相应增删，且操作可被审计；`viewer` 发起同请求返回 403

#### Scenario: 配置不改变运行时（阶段 2 脚手架）
- **WHEN** admin 配置了能力或群白名单
- **THEN** 仅平台侧存储变更；agent 运行时行为在本阶段不受影响（materialize 接线与准入闸属阶段 3）

