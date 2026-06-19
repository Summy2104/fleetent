# shared-memory-admin-api Specification

## Purpose
Define the platform HTTP control-plane surface for tenant and team scoped shared memory.
## Requirements
### Requirement: 共享记忆管理 HTTP API

平台 SHALL 在 `/admin/memory/shared` 下暴露共享记忆条目的管理 HTTP API。所有端点 SHALL 使用 `Authorization: Session <token>` 做管理员鉴权，并通过 `fleetent.memory` 公共 API 读写 tenant-scoped shared memory。创建成功 SHALL 返回 201。

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

