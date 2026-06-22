## Context

grounding 已核实：
- `users.email`：可空、**无唯一约束**；`get_by_email(email)` = `WHERE email = :email`（全局、精确、无 tenant、无规范化）。
- `create_user(name, email=None, tenant_id="default") → (User, plaintext_key)`（**总是发一个 api_key**）。
- IM `platform/im_gateway_management/identity.py::get_or_create(platform, platform_user_id, edge_tenant)`：按 `(platform,platform_user_id)` 查 im_users，没有就 `create_user(name=f"{platform}:{puid}", tenant_id=edge_tenant)` + 写 im_users。**不看 email**。
- im_users 已是纯映射（089 落地）：`(id, platform, platform_user_id, user_id, created_at, meta_json)` + `UNIQUE(platform,platform_user_id)` + FK→users。
- `user-store` spec 有"user_store does not depend on platform"约束。

## Goals / Non-Goals

**Goals:**
- email 成为租户内规范化唯一的跨渠道 join key（可空、partial unique）。
- 一个边缘无关的 `resolve_or_provision`：有 verified email → lookup-or-link-or-create by `(tenant, norm_email)`；无 → channel-keyed。
- IM provisioning 路由经它（有 email 时）。
- merge policy = attach-only，绝不合并已存在 user。

**Non-Goals:**
- OIDC（#1）、IM-edge 取 email（#4）、手动 `/link`（#5）、已存在 user 合并/重归属（post-v1）。
- 不动 im_users 结构（已 slim）。

## Decisions

- **D1 · 规范化在写入侧（normalize-on-write）。** `create_user` / `set_profile` 写 email 前 `lower(trim)`；partial unique 索引直接作用于已规范化的值。`get_by_email(tenant_id, email)` 比较前同样 `lower(trim)`。→ 索引/查询一致，无需函数索引。
- **D2 · 唯一约束 = partial `UNIQUE(tenant_id, email) WHERE email IS NOT NULL`**（SQLite partial index）。email 可空、无 email 用户不参与。
- **D3 · `resolve_or_provision` 放平台侧**（`im_gateway_management/identity.py` 扩展或同包新模块），因为它**同时碰 user_store(users) 和 im_users**——不能放 `user_store`（守"user_store 不依赖 platform"）。契约：
  `resolve_or_provision(tenant, *, verified_email=None, channel=None, platform_user_id=None) -> User`
  - verified_email 给：`get_by_email(tenant, email)` 命中→（有 channel 且 im_users 无此映射则 attach）返回；未命中→`create_user(email, tenant)` + attach channel。
  - 无 email：现行 channel-keyed `create_user` + map。
  edge 各自提供 tenant + email（IM=edge_tenant + (#4 取的)email；OIDC #1=IdP email + IdP/配置定的 tenant）。
- **D4 · attach-only，绝不 merge（决策 1）。** 若 channel 身份**已**在 im_users 有映射 → 用现映射，**不**因 email 改挂、**不**合并目标 user。仅"无映射的 channel 身份"才 attach 到 email-keyed user。
- **D5 · `get_by_email` 加 tenant 参数 → survey 所有调用方补 tenant。** 改签名后全仓 grep 调用点逐个补 edge_tenant / 上下文 tenant。
- **D6 · 迁移（Alembic 管理库）**：(1) backfill 现有 `users.email` 为 `lower(trim)`；(2) 检测同租户规范化重复 → **有则报告+中止**（不自动合并，决策 6）；(3) 建 partial unique index。向后兼容：无 email 行不受影响。

## Risks / Trade-offs

- **`get_by_email` 改签名波及面**：是公开函数，调用方可能不止一处。D5 的 survey 必须穷尽，漏改 = 编译/运行错或漏 tenant。先 grep 全量调用点再动。
- **迁移撞存量重复**：真实库 email 多为空、真重复概率低；但迁移必须**显式检测+中止+报告**，绝不静默合并/丢数据（决策 1/6 的迁移面）。
- **`create_user` 总发 key**：email-keyed user（将来 OIDC web 用户）也会拿到一个 api_key——可接受（每个 user 一把 key 是现有模型），但注意别把"web 登录用户"和"程序 key"语义混淆；本切片不改这点，记为观察。
- **race：并发首触发同 email**：两个渠道同时首次带同一 email → 可能并发 create。靠 partial unique 兜底（第二个 insert 撞唯一约束→捕获后转 lookup-link），provisioning 要处理"insert 撞唯一→改走 lookup"（镜像现有 get_or_create 的 `INSERT OR IGNORE` 竞态处理）。
- **规范化口径**：仅 `lower(trim)`，**不剥 plus-addressing**（决策 2）——`alice+x@` 视为不同地址。
