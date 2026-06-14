# slim-im-users-to-identity-map

> IM 访问模型（[im-access-model](../../../docs/architecture/im-access-model.md) §11）**阶段 3b**：把 `im_users` 瘦身为纯 `platform_user_id ⇄ user_id` 双向身份映射——删 `owner_id` + `allowed`，补 FK，provisioning 落 `edge_tenant`，封禁迁 `users.status`。**独立于阶段 3 的闸**（碰 im_users / identity.py / server.py resolver / users，不同文件）。head=088（新迁移 089，**勿硬编码**）；已核 `knowledge-base-standalone-service` 不碰。

## Why

`im_users` 当前职责被两件不该在它身上的事撑大（审计 2026-06-14）：
- **`owner_id`**（实为 agent 名、误名）：纯身份映射不需要作用域列——租户在 User 身上（`users.tenant_id`），全局身份模型（一个 `(platform, platform_user_id)` = 一个内部 User）。
- **`allowed`**：与新访问模型**重复且 runtime 不被强制**——`check_allowed_by_user_id` 无任何准入路径消费方（已验证）；访问由 `user_agents`/`allow_users`（阶段 3 闸）决定，封禁应由 `users.status` 决定。

且暴露一个隐患：**IM 路径当前对"封禁"实际不强制**（`allowed` 死、`users.status` 在 IM 渠道担保路径未被查）。本阶段顺手接上。

## What Changes

### im_users 瘦身（Alembic）
- 新迁移（append after head、勿硬编码）：**批量重建 `im_users`**——删 `owner_id`、`allowed`，UNIQUE 改 `(platform, platform_user_id)`，补 **FK `user_id`→users.id**（ondelete 按 tenancy 风格：删 user 级联清其 IM 映射 = CASCADE）。
- 列保留：`id` / `platform` / `platform_user_id` / `user_id` / `created_at` / `meta_json`。
- 数据迁移：现有跨 owner 多行按 `(platform, platform_user_id)` 去重为一行（跨 agent 复用本就共享 user_id；pre-launch 窗口可重置）。

### resolver（identity.py + server.py）
- `get_or_create(platform, platform_user_id, edge_tenant)`：按 `(platform, platform_user_id)` 查/建；首见时 `create_user(tenant_id=edge_tenant)`（edge_tenant = 收消息 bot 的 `agent.tenant_id`）——**修"新用户落 default、非 default 租户 agent 被守卫拒"的 bug**。去掉 `owner_id` 参数的存储用途（server.py 仍由 agent 名推 edge_tenant 喂进来）。
- `_resolve_im_identity`：解析出 User 后**新增 `user.status=="blocked"→拒**（接上当前缺失的 IM 封禁强制）；保留既有 tenant-mismatch 守卫。

### 封禁/准入归位（im-user-allowlist 瘦身）
- **封禁** → `users.status`（封整个 User）；admin block/restore 操作 `users.status`、不再操作 `im_users.allowed`。
- **approve/pending/default-allowed** → 移除：访问在新模型是 `user_agents` 授权（默认关），无"per-IM 审批/pending"概念；"授权某人用某 agent" = user-bind（agent-admin-api 已有）。
- **统一身份视图**（列 IM 身份）保留（就是 im_users 列表）。

## Capabilities

### Modified Capabilities
- `im-user-mapping`: `im_users` schema 去 `owner_id`/`allowed`、UNIQUE 改 `(platform, platform_user_id)`、补 FK `user_id`→users；唯一性从"per-owner 多行复用同 user_id"改为"全局 `(platform, platform_user_id)` 唯一"；首见 provisioning 落 `edge_tenant`；封禁经 `users.status` 在平台 resolver 强制。
- `im-user-allowlist`: 移除基于 `allowed` 的 approve/pending/default-allowed（被 `user_agents` 访问模型取代）；block/restore 改作用于 `users.status`；保留统一身份视图。

## Impact

- **owning package**：`platform`（Alembic + `im_gateway_management/identity.py` + `im_gateway_management` 的 allowlist admin + `server.py` resolver）；`user_store`（status 封禁查询，已存在）。
- **public API surface**：`get_or_create` 签名变（owner_id→edge_tenant，内部）；im-user-allowlist admin API 的 approve/pending 端点移除、block/restore 改打 users.status。
- **owned tables**：`im_users` 删 2 列 + 改 UNIQUE + 补 FK；无新表。
- **config namespace**：无。
- **cross-module dependencies**：resolver 注入契约不变（platform 注入、standalone 透传原生 id）；agent 零 platform import 不变。
- **migration / shim plan**：append after head（089，勿硬编码）；batch 重建 im_users（去重 (platform,puid)）；forward-only + downgrade 反向（重建 owner_id/allowed 列，数据不复原）。
- **相邻切片**：阶段 4（改名）在其后；whatsapp owner-level（§9）与 im_connectors.owner_id 是另轨；已核无 collision；apply 前 pull 确认 head。
