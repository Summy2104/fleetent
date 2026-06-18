# tenant-admin-api Specification

## Purpose
Define the platform HTTP control-plane surface for tenant and team administration.

## Requirements
### Requirement: 租户与团队管理 HTTP API

平台 SHALL 在 `/admin/tenancy` 下暴露租户与团队管理 HTTP API，覆盖创建租户、列举租户、创建团队、设置用户租户归属、设置 tenant/team 审批人。所有端点 SHALL 使用 `Authorization: Session <token>` 做管理员鉴权，底层复用现有 tenancy store。

#### Scenario: 创建租户

- **WHEN** admin 调用 `POST /admin/tenancy/tenants` 并提交 `name`
- **THEN** 系统创建租户并返回租户对象

#### Scenario: 列举租户

- **WHEN** admin 调用 `GET /admin/tenancy/tenants`
- **THEN** 系统返回所有租户列表

#### Scenario: 创建团队

- **WHEN** admin 调用 `POST /admin/tenancy/teams` 并提交 `tenant_id` 与 `name`
- **THEN** 系统在对应租户下创建团队并返回团队对象

#### Scenario: 设置用户租户归属

- **WHEN** admin 调用 `POST /admin/tenancy/users/{user_id}/tenant` 并提交 `tenant_id`
- **THEN** 系统更新该用户的 tenant 归属

#### Scenario: 设置审批人

- **WHEN** admin 调用 `PATCH /admin/tenancy/approvers/{entity_id}` 并提交 `entity_type` 与 `approver_user_id`
- **THEN** 系统更新对应 tenant 或 team 的审批人

#### Scenario: 未鉴权请求被拒绝

- **WHEN** 请求未携带合法 `Authorization: Session <token>`
- **THEN** 系统返回 401

#### Scenario: 非 admin 写请求被拒绝

- **WHEN** viewer 角色用户调用写端点
- **THEN** 系统返回 403

### Requirement: 租户管理 router 接线

`server.py` SHALL 注册 tenancy admin router，使 `/admin/tenancy/*` 在平台服务中可达。

#### Scenario: 平台服务提供租户管理端点

- **WHEN** 平台服务启动后调用 `GET /admin/tenancy/tenants`
- **THEN** 系统返回业务响应，而不是 404
