## Why

租户管理 CLI（`create-tenant` / `list-tenants` / `create-team` / `set-user-tenant` / `set-approver`）**直接 import `tenancy_store` 写管理库表**，绕开平台 server——管理库因此有两个并行写入口（HTTP `/admin/tenancy/*` 和 CLI），CLI 这条还绕过了 session 鉴权与 HTTP 审计中间件，且要求 CLI 宿主能直连管理库。租户/团队/审批人创建是**业务控制面操作**（发生在 server 已起、admin 已在之后），不是 bootstrap，应只走平台 HTTP API。本 change 删除这 5 条 CLI，并把"业务控制面操作不得直写管理库、必须走 HTTP"这条边界原则固化进 spec，防止回潮。

## What Changes

- **删除 5 条租户 CLI**：从 `admin_cli/main.py` 的 `_COMMAND_MODULES` 移除 `tenancy`，删除 `admin_cli/tenancy.py`。租户管理改为只经 HTTP `/admin/tenancy/*`。
- **删除对应 CLI 测试**：`tests/integration/test_tenancy_admin.py` 中的 `*_cli` 测试（保留 `test_api_*` HTTP 测试）。
- **固化边界原则（spec）**：`module-boundaries` 新增 requirement——admin CLI 直写管理库仅限 (a) 真 bootstrap、(b) spec 认可的基础设施供给（node）、(c) 危险宿主级维护；业务控制面操作 MUST 走 HTTP、MUST NOT 有绕过 server 的直写 CLI。
- **收紧 tenancy provisioning spec**：`tenancy-entities` 的「最小 provisioning」由"admin CLI 或 API"改为"平台 HTTP API"。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities

- `module-boundaries`：ADD「Admin CLI 直写管理库的边界」requirement。
- `tenancy-entities`：MODIFY「最小 provisioning(admin)」——provisioning 入口为平台 HTTP API，不再经直写管理库的 CLI。

## Impact

**owning package**：`src/fleetent/platform/admin_cli/main.py`，删除 `admin_cli/tenancy.py`

**public API surface（移除）**：`fleetent admin create-tenant` / `list-tenants` / `create-team` / `set-user-tenant` / `set-approver`（HTTP `/admin/tenancy/*` 不变，为唯一入口）

**owned tables**：无 schema 变更（仍是 `tenants`/`teams`/`users.tenant_id`，写入路径收敛为 HTTP）

**config namespace**：无　**migration**：无

**cross-module dependencies**：删 CLI 后 `admin_cli` 不再 import `platform.tenancy.store`；HTTP 路由层依赖不变

**验证可删**：HTTP `tenancy/admin_api.py` 已有全部 5 条等价端点且接线（add-platform-admin-apis 落地）；`seed-builtin-admin`（bootstrap）建内置 admin → 登录拿 session → 租户全走 HTTP；default 租户由迁移建，无 bootstrap 依赖。
