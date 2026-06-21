## MODIFIED Requirements

### Requirement: 最小 provisioning(admin)
系统 **MUST** 提供管理员可用的最小 provisioning 入口，经**平台 HTTP API**（`/admin/tenancy/*`）：创建主体、创建团队、设置某 user 的 `tenant_id`、设置主体/团队的 `approver_user_id`。这些操作 **MUST** 受现有 admin 鉴权（session token）保护并写审计，**MUST NOT** 经绕过 server 直写管理库的 CLI 提供（见 module-boundaries「Admin CLI 直写管理库的边界」）。

#### Scenario: 建主体并分配用户
- **WHEN** admin 经 HTTP API 创建主体 "A主体" 并把用户 U 的 `tenant_id` 设为它
- **THEN** "A主体" 行存在，U 的 `tenant_id` 指向它，且操作被审计

#### Scenario: provisioning 无直写 CLI 路径
- **WHEN** 查看 `fleetent admin` 子命令
- **THEN** 不存在 create-tenant / create-team / set-user-tenant / set-approver 等直写管理库的命令；provisioning 仅经 HTTP API
