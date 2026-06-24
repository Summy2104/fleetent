## Why

`im_users` 表记录"内部 user_id ↔ IM 渠道外部身份"映射，store 逻辑（`im_gateway_management/identity.py`）已完备：`list_all` / `get_im_user` / `attach_identity` / `delete_im_identity` / `rebind_im_identity` 等一应俱全。但管理员**没有一个聚焦的入口**直观查看"哪个外部身份绑到哪个内部用户"并手动增删绑定：

- 现有 IM-user 路由（`GET/POST/DELETE /admin/im-users*`）零散挂在 `user_admin_api.py` 里，且列表（`list_all`）只带出 `user_id`，看不到该用户的**用户名 / 邮箱**——管理员要再翻 Users 页才知道是谁。
- 前端只有 Users 页右侧一小块 "IM identities" 子区块（侧重 block/restore/rebind），没有专门的"用户-IM 关系"管理页。

本变更新增一个**专属管理页**（后端 admin API + 前端页），让管理员一屏看清映射全貌（平台 / 外部 ID / 内部用户名+邮箱）并直接新增、删除绑定。

## What Changes

- **后端**：新增 `im_gateway_management/im_identity_admin_api.py`（独立 router，前缀 `/admin/im-identities`，与既有 `/admin/im-users` 不冲突），提供：
  - `GET /admin/im-identities` — 列出全部映射，**join users 带出用户名 / 邮箱**（viewer+admin 可读）。
  - `POST /admin/im-identities` — 新增绑定 `{platform, platform_user_id, user_id}`（admin only；目标用户不存在→404，`(platform, platform_user_id)` 已映射→409）。
  - `DELETE /admin/im-identities/{im_user_id}` — 删除绑定（admin only；不存在→404）。
  - session 认证对齐 `user_admin_api`（`Authorization: Session <token>`，本模块自带 `_session_user`/`_require_admin` helper，不 import agent loop，可独立测试）。
- **store**：在 `identity.py` 补两个查询（named parameters），并经 `__init__` re-export：
  - `list_mappings()` — 映射全表 join users 带出 `user_name` / `user_email`。
  - `create_mapping(platform, platform_user_id, user_id, actor=None)` — 校验目标用户存在 + 唯一约束冲突，写审计 `create_im_user`，返回新映射行。
  - 删除复用既有 `delete_im_identity`。
- **server.py**：仅加 1 行 import + 1 行 `include_router`。
- **前端**：新增 `frontend/src/features/im-identities/{api.ts,page.tsx}`（TanStack Query + MSW + TDD，照 `features/nodes/` 范式）：列出映射、表单新增、删除。`app/routes.tsx` 加侧边栏入口 + `<Route path="/im-identities">`，标题"用户-IM 关系"。

## Capabilities

### New Capabilities
- `im-identity-admin-ui`：React SPA 中专属的"用户-IM 关系"页，列出 IM 身份映射（平台 / 外部 ID / 内部用户名+邮箱）并支持管理员新增、删除绑定。

### Modified Capabilities
- `im-user-mapping`：新增"管理员可经 `/admin/im-identities` admin API 列出（带内部用户名/邮箱）、新增、删除 IM 身份映射"的要求。

## Impact

- **新增**：
  - `src/fleetent/platform/im_gateway_management/im_identity_admin_api.py`
  - `frontend/src/features/im-identities/{api.ts,page.tsx,api.test.tsx,page.test.tsx}`
  - 后端 integration 测试 `tests/integration/test_im_identity_admin_api.py`
- **改动**：
  - `src/fleetent/platform/im_gateway_management/identity.py`（+`list_mappings`/`create_mapping`）与 `__init__.py`（re-export）
  - `src/fleetent/server.py`（import + include_router，1+1 行）
  - `frontend/src/app/routes.tsx`（nav + Route）与 `routes.test.tsx`（断言）
- **边界**：
  - owning package：`platform`（`im_gateway_management` 子包）
  - public API surface：新增 `im_gateway_management.list_mappings`、`im_gateway_management.create_mapping`、`im_identity_admin_api.router`
  - owned tables：**无新增**——复用既有管理表 `im_users`（`UNIQUE(platform, platform_user_id)` + `FK user_id→users(id) ON DELETE CASCADE`），不动 schema
  - config namespace：无
  - cross-module dependencies：依赖 `fleetent.auth`、`fleetent.user_store` 的 public API（与其他 admin router 一致）；router 依赖 `im_gateway_management` public API
  - migration / shim plan：无（无模块移动、无 schema 变更）
- **不碰**：agent 运行时（runtime/session/im_gateway/...）、agent 侧表、其他 platform 域。纯 platform 服务 + 前端。**合并由主会话串行做。**
