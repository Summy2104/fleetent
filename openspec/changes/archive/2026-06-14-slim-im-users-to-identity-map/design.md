# 设计：slim-im-users-to-identity-map（IM 访问模型阶段 3b）

详见 im-access-model.md §11。要点 + apply 时关键背景：

## D1 — 为什么 owner_id / allowed 都删（非重键、非迁移）
- `owner_id`（=agent 名）：纯映射不需作用域列，租户在 User 身上。全局身份：`(platform, platform_user_id)` 全局唯一 → 一个内部 User。
- `allowed`：**runtime 已不被强制**（`check_allowed_by_user_id` 无准入消费方，已 grep 验证）。访问=user_agents（闸）、封禁=users.status，三层塌两层。

## D2 — 隐患修复：IM 封禁当前其实没生效
- `allowed` 死；`users.status` 在 IM 渠道担保路径（`resolve_principal` "no user_store read"）未被查。故"封一个 IM 用户"当前无运行时效果。
- 本阶段在**平台侧 resolver `_resolve_im_identity`**（本就读 im_identity、属平台侧）加 `user.status=="blocked"→拒`。这是平台侧、不破坏 agent 解耦（agent 侧闸仍零 platform DB）。

## D3 — 新 IM 用户的默认行为不变
- phase 3 已让访问默认关（user_agents 空→用不了任何 agent）。删 allowed **不改这个**：新 IM 用户身份照建（im_users 行 + create_user），但用不了 agent 直到被 user-bind 授权。"approve" = user-bind（已有端点），不是 im_users.allowed。

## D4 — provisioning 落 edge_tenant（bug 修复）
- 现状 `create_user` 不传 tenant→落 default；守卫要 user.tenant==edge_tenant→非 default 租户 agent 拒所有新 IM 用户。
- 修：`get_or_create(..., edge_tenant)` 首见 `create_user(tenant_id=edge_tenant)`。edge_tenant 由 server.py 从 agent 名（连接器）推 `agent.tenant_id` 后喂入。

## D5 — 迁移（im_users batch 重建）
- append after head（089，勿硬编码）。删 owner_id/allowed、UNIQUE→(platform,platform_user_id)、补 FK user_id→users ON DELETE CASCADE（删 user 清其 IM 映射，合理）。
- 数据：现有跨 owner 多行 → 按 (platform, platform_user_id) **去重为一行**（跨 agent 复用本就同 user_id；若有冲突取任一，pre-launch 可重置）。
- downgrade 反向重建 owner_id/allowed 列（数据不复原）。

## D6 — owner 塌缩进 tenant 的全景（本阶段是第一刀）
im_users(本阶段删 owner_id) + im_channel_allowlist(descope，B 清单) + im_connectors(待 §9 whatsapp) 三处 owner_id 全退役后，模型只剩 tenant 一个作用域轴。本阶段只动 im_users。
