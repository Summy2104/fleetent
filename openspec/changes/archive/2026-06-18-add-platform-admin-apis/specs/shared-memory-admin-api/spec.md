## ADDED Requirements

### Requirement: 共享记忆管理 HTTP API

平台 SHALL 在 `/admin/memory/shared` 下暴露共享记忆条目的 CRUD HTTP API。所有操作 MUST 要求 admin 角色（session token 鉴权）。底层调用 `fleetent.memory` 公共 API，与 `fleetent-admin memory shared` CLI 功能等价。

#### Scenario: 列举共享记忆

- **WHEN** admin 调用 `GET /admin/memory/shared?scope_type=<type>&scope_id=<id>`
- **THEN** 系统返回该 scope 下的共享记忆条目列表

#### Scenario: 创建共享记忆

- **WHEN** admin 调用 `POST /admin/memory/shared`，body 含 `scope_type`、`scope_id`、`type`、`content`、`actor`
- **THEN** 系统创建共享记忆条目并返回 201 及条目对象

#### Scenario: 更新共享记忆

- **WHEN** admin 调用 `PATCH /admin/memory/shared/{item_id}`，body 含 `content`（或 `type`/`status`）和 `actor`
- **THEN** 系统更新对应条目并返回更新后对象

#### Scenario: 归档共享记忆

- **WHEN** admin 调用 `POST /admin/memory/shared/{item_id}/archive`，body 含 `actor`
- **THEN** 系统将条目状态置为 archived

#### Scenario: 非 admin 访问被拒绝

- **WHEN** viewer 角色用户调用任意共享记忆端点
- **THEN** 系统返回 403

#### Scenario: 归档条目默认不在列表中

- **WHEN** admin 调用 `GET /admin/memory/shared` 不带 `include_archived=true`
- **THEN** 已归档条目不出现在响应列表中
