## ADDED Requirements

### Requirement: 租户管理 HTTP API

平台 SHALL 在 `/admin/tenancy` 下暴露租户与团队的 CRUD HTTP API，所有写操作 MUST 要求 admin 角色（session token 鉴权）。这些端点与 `fleetent-admin` CLI 的 `create-tenant`/`list-tenants`/`create-team`/`set-user-tenant`/`set-approver` 功能等价，底层调用相同 store 函数。

#### Scenario: 创建租户

- **WHEN** admin 以合法 session token 调用 `POST /admin/tenancy/tenants`，body 含 `name`
- **THEN** 系统创建租户并返回 201 及租户对象（含 `id`、`name`、`status`）

#### Scenario: 列举租户

- **WHEN** admin 调用 `GET /admin/tenancy/tenants`
- **THEN** 系统返回所有租户列表

#### Scenario: 创建团队

- **WHEN** admin 调用 `POST /admin/tenancy/teams`，body 含 `tenant_id` 和 `name`
- **THEN** 系统在对应租户下创建团队并返回 201

#### Scenario: 配置审批人

- **WHEN** admin 调用 `POST /admin/tenancy/approver`，body 含 `tenant_id`（或 `team_id`）和 `approver_user_id`
- **THEN** 系统更新对应实体的 `approver_user_id` 字段

#### Scenario: 非 admin 访问被拒绝

- **WHEN** viewer 角色用户调用任意写操作端点
- **THEN** 系统返回 403

#### Scenario: 未鉴权请求被拒绝

- **WHEN** 请求不携带 `Authorization: Session <token>` 头
- **THEN** 系统返回 401

### Requirement: 租户管理 API 接线

`server.py` SHALL 将 `tenancy/admin_api.py` 的 router 注册到 FastAPI app（`include_router`），使上述端点在平台服务启动后可访问。

#### Scenario: 平台启动后租户端点可达

- **WHEN** 平台服务启动后，admin 调用 `GET /admin/tenancy/tenants`
- **THEN** 返回 200，而非 404
