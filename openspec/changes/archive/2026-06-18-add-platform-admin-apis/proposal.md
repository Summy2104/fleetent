## Why

平台控制面存在四块管理操作（租户/团队管理、节点注册管理、共享记忆管理、KB 实体提取触发）目前只有 `fleetent-admin` CLI 入口，平台 HTTP API 缺位。这使平台无法作为唯一控制面真相源，后续 CLI 精简（`slim-admin-cli`）也无法推进。

## What Changes

- **新增租户/团队管理 HTTP API**：`POST/GET /admin/tenants`、`POST /admin/tenants/{id}/teams`、`POST /admin/tenants/{id}/users`、`PATCH /admin/tenants/{id}/approver`，覆盖 `create-tenant`、`list-tenants`、`create-team`、`set-user-tenant`、`set-approver` 五条 CLI 命令的等价 HTTP 路径。
- **新增节点管理 HTTP API**：`POST/GET /admin/nodes`（注册/列举）、`DELETE /admin/nodes/{id}`（注销）、`POST/DELETE /admin/nodes/{id}/pin`（pin/unpin agent），覆盖 `node register/list/deregister/pin/unpin` 五条 CLI 命令。
- **新增共享记忆管理 HTTP API**：`GET/POST /admin/memory/shared`、`PATCH /admin/memory/shared/{id}`、`POST /admin/memory/shared/{id}/archive`，覆盖 `memory shared list/create/update/archive` 四条 CLI 命令。
- **新增 KB 实体提取触发 API**：`POST /admin/kb/{kb_id}/extract-entities`，覆盖 `kb extract-entities` CLI 命令。

## Capabilities

### New Capabilities

- `tenant-admin-api`：平台 HTTP API，提供租户/团队 CRUD、用户-租户归属配置、审批人配置。
- `shared-memory-admin-api`：平台 HTTP API，提供共享记忆条目的 CRUD 与归档。

### Modified Capabilities

- `agent-node-registry`：新增节点管理 HTTP API surface（`/admin/nodes/*`），原有 CLI-only 注册/注销/pin 操作改为经 HTTP API 执行。
- `kb-admin-api`：新增实体提取触发端点（`POST /admin/kb/{kb_id}/extract-entities`）。

## Impact

**owning package**：`platform/`（新增 router 文件 + store 扩展）

**public API surface（新增）**：
- `POST   /admin/tenants`
- `GET    /admin/tenants`
- `POST   /admin/tenants/{id}/teams`
- `POST   /admin/tenants/{id}/users`
- `PATCH  /admin/tenants/{id}/approver`
- `POST   /admin/nodes`
- `GET    /admin/nodes`
- `DELETE /admin/nodes/{id}`
- `POST   /admin/nodes/{id}/pin`
- `DELETE /admin/nodes/{id}/pin`
- `GET    /admin/memory/shared`
- `POST   /admin/memory/shared`
- `PATCH  /admin/memory/shared/{id}`
- `POST   /admin/memory/shared/{id}/archive`
- `POST   /admin/kb/{kb_id}/extract-entities`

**owned tables**：无新表（`tenants`/`teams` 由 `tenancy-entities` 已建；`nodes` 由 `agent-node-registry` 已建；shared memory 表由现有 memory store 已建）

**config namespace**：无新增配置项

**cross-module dependencies**：新增 router 依赖现有 `platform/tenant_store`、`platform/node_store`（`agent-node-registry`）、`memory/shared_memory_store`、`knowledge_base/`（KB extract）；无新增跨模块契约

**migration / shim plan**：无持久层改动，只新增 HTTP 路由层
