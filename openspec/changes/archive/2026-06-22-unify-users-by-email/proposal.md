## Why

要让"同一个员工跨渠道 = 同一个 user"成立，需要一个**按 email 并号的身份 provisioning 地基**。现状缺口：
- `users.email` 可空、**无唯一约束**，`get_by_email` 是**全局精确匹配**（`WHERE email = :email`，无 tenant、无大小写规范化）。
- IM 的 `get_or_create`（`platform/im_gateway_management/identity.py`）按 `(platform, platform_user_id)` 建 user、**完全不看 email** → 每个渠道身份各自一个 user，不并号。

这块是车道 D 的**共享地基**：被 #1（OIDC/web 登录）和 #4（IM-edge）**两个消费方**共用——两边都拿到 verified email 后要落到同一个 email-keyed user。先打一次，之后 #1 / #4 各自接上、可并行。

> 这是 `docs/architecture/identity-channel-ingress.md` 切片 #2。**好消息**：im_users 的结构演进（3b）已在 migration 089 落地（已是纯 `(platform, platform_user_id)→user_id` 映射 + `UNIQUE(platform,platform_user_id)` + FK→users），故本切片**不动 im_users 结构**，只加 email 并号。

## What Changes

- **email 成为租户内跨渠道 join key**：users 加 **partial `UNIQUE(tenant_id, email)`（仅 email 非空时）**；email 在写入时 **规范化为 `lower(trim(email))`**（决策 2）；`get_by_email` 改为 **tenant 范围 + 规范化匹配**。email 保持**可选**——内置 admin / service principal / 纯 IM 用户无 email，不参与并号、不受影响。
- **email-keyed provisioning（平台侧）**：新增边缘无关的解析函数 `resolve_or_provision(tenant, *, verified_email=None, channel=None, platform_user_id=None) -> User`：
  - 给 verified_email → 按 `(tenant, lower(email))` 找到则返回（有 channel 且未映射则**挂上去**）；没找到则建 email-keyed user + 挂 channel。
  - 无 email → 维持现行 channel-keyed 建 user。
- **IM 路由经它**：`get_or_create` 在拿得到 verified email 时走 `resolve_or_provision`（email 由 edge 提供；当前 Slack adapter 未取 email 则等 #4 补，本切片不依赖）。
- **merge policy（决策 1）**：只把**还没有 user 的 channel 身份**挂到 email-keyed user；**绝不自动合并两个已存在的 user**（已存在双 user → 人工/admin，post-v1）。

### 不在本切片（deferred）
- OIDC 登录本身（#1，会调用本切片的 `resolve_or_provision`）。
- IM-edge 下沉 node + Slack/OIDC 取 email 的 edge 实现（#4）。
- 手动 `/link`（#5，处理"无 email 先来、有 email 后到"的两 user 情形）。
- 两个已存在 user 的合并 / 错绑数据重归属（post-v1）。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `user-store`: `users.email` 成为**租户内规范化唯一**（partial UNIQUE(tenant_id, email)、写入 lower+trim）；`get_by_email` 改为 tenant 范围 + 规范化；email 作为跨渠道 join key（仍可空）。
- `im-user-mapping`: IM provisioning 在拿到 verified email 时经 email-keyed `resolve_or_provision`（lookup-or-link by `(tenant,email)`），把渠道身份挂到既有 email-keyed user；无 email 时维持现行 channel-keyed 建 user。

## Impact

- **owning packages**：`user_store`（email 唯一约束 + 规范化 + tenant 范围 `get_by_email`，**保持不依赖 platform**）；`platform/im_gateway_management`（`resolve_or_provision` + `get_or_create` 路由，碰 im_users + 调 user_store）
- **public API surface**：`user_store.get_by_email` 签名加 tenant；新增 `resolve_or_provision(...)`（供 #1 OIDC / #4 IM 复用）；`create_user` 写入规范化 email
- **owned tables**：`users`（加 partial `UNIQUE(tenant_id, email)`；**无新列**）；`im_users` 不变（已 slim）
- **config namespace**：无
- **cross-module dependencies**：platform provisioning 调 `user_store`（允许）；`user_store` 仍不依赖 platform（守 user-store spec 既有要求）；不碰 agent 运行时
- **migration / shim**：Alembic（管理库）：先 backfill 现有 email 为 `lower(trim)`，再加 partial unique index；**若现存 `(tenant, lower(email))` 重复 → 迁移报告并中止、不自动合并**（决策 6）。`get_by_email` 旧调用方需补 tenant（survey + 改）
- 与并行的 #3(已落地) / kb-retrieval-audit / #1 / #4 关系：本切片是 #1/#4 的前置地基；只碰 user_store + im_gateway_management，**不碰** server.py/forwarder/agent_app（与在飞的改动零重叠）
