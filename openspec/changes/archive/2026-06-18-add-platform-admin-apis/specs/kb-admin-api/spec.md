## ADDED Requirements

### Requirement: KB 实体提取触发端点

系统 SHALL 在现有 `kb_admin_api` router 中新增 `POST /admin/kb/{kb_id}/extract-entities` 端点，供管理员手动触发指定 KB 的实体提取任务。功能等价于 `fleetent admin kb extract-entities` CLI 命令。

#### Scenario: 触发实体提取

- **WHEN** admin 调用 `POST /admin/kb/{kb_id}/extract-entities`
- **THEN** 系统对该 KB 启动实体提取流程并返回 202 Accepted（任务异步执行）

#### Scenario: KB 不存在时返回 404

- **WHEN** admin 以不存在的 `kb_id` 调用触发端点
- **THEN** 系统返回 404，不启动任何任务

#### Scenario: 非 admin 访问被拒绝

- **WHEN** viewer 角色用户调用该端点
- **THEN** 系统返回 403
