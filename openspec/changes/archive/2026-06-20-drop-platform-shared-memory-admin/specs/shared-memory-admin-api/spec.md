## REMOVED Requirements

### Requirement: 共享记忆管理 HTTP API
**Reason**: 共享记忆是 agent 侧数据且有 agent 侧治理生命周期(reflection 提议→审批门→apply)。该平台侧直写 HTTP API 绕过治理、放错了层(complete-admin-api-coverage 加入时未察觉已有 proposal/apply 治理)。审查确认无 admin UI 消费它。整个 capability 随本 change 下线。
**Migration**: 共享记忆改动走 agent 侧 reflection proposal/apply 生命周期。若需主动手动编辑,作为 agent 侧能力另行 propose,不在平台开直写旁路。

#### Scenario: 列举共享记忆

- **WHEN** admin 调用 `GET /admin/memory/shared?scope_type=<type>&scope_id=<id>`
- **THEN** 系统返回该 scope 下的共享记忆条目列表

#### Scenario: 创建共享记忆返回 201

- **WHEN** admin 调用 `POST /admin/memory/shared` 并提交 `scope_type`、`scope_id`、`type`、`content`
- **THEN** 系统创建共享记忆条目并返回 201 及条目对象

#### Scenario: 更新共享记忆

- **WHEN** admin 调用 `PATCH /admin/memory/shared/{item_id}` 并提交 `content`、`type` 或 `status`
- **THEN** 系统更新对应条目并返回更新后对象

#### Scenario: 归档共享记忆

- **WHEN** admin 调用 `POST /admin/memory/shared/{item_id}/archive`
- **THEN** 系统将条目状态置为 `archived`

#### Scenario: 归档条目默认不在列表中

- **WHEN** admin 调用 `GET /admin/memory/shared` 且未设置 `include_archived=true`
- **THEN** 已归档条目不出现在响应列表中

#### Scenario: 非 admin 请求被拒绝

- **WHEN** viewer 角色用户调用任意共享记忆写端点
- **THEN** 系统返回 403
