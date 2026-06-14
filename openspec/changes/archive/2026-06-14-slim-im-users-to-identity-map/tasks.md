# slim-im-users-to-identity-map Tasks

> TDD：实现 task 先测试见红 → 实现见绿（最窄命令）；测试在实现之前。迁移号 append after head、**勿硬编码**。不改任何 IM 命名（那是阶段 4）。

## 1. 迁移：im_users 瘦身（Alembic）

- [x] 1.1 [测试] integration：head 后 `im_users` 无 `owner_id`/`allowed` 列；UNIQUE 为 `(platform, platform_user_id)`；FK `user_id`→users.id ON DELETE CASCADE；列为 id/platform/platform_user_id/user_id/created_at/meta_json（先红）
- [x] 1.2 [测试] integration：删一个 user → 其 im_users 行级联清空（先红）
- [x] 1.3 [实现] 新迁移（append after head、勿硬编码）：batch 重建 im_users（删 owner_id/allowed、改 UNIQUE、加 FK）；数据按 `(platform, platform_user_id)` 去重为一行；downgrade 反向重建列（数据不复原）→ 1.1/1.2 转绿

## 2. resolver：身份映射 + edge_tenant provisioning + 封禁强制

- [x] 2.1 [测试] integration：`get_or_create(platform, platform_user_id, edge_tenant)` 首见时 `create_user(tenant_id=edge_tenant)`；已存在则返回同 user；按 (platform, puid) 唯一（先红）
- [x] 2.2 [测试] integration：`_resolve_im_identity` 对 `users.status=="blocked"` 的 user **拒**（IMIdentityResolutionError）；非 default 租户 agent 的新 IM 用户**不再被 tenant-mismatch 误拒**（因落 edge_tenant）（先红）
- [x] 2.3 [实现] `identity.py` get_or_create 去 owner_id、按 (platform, puid) 键、首见 create_user(edge_tenant)；`server.py _resolve_im_identity` 加 users.status 封禁检查、把 edge_tenant 传入 get_or_create → 2.1/2.2 转绿

## 3. im-user-allowlist 瘦身（封禁归 users.status）

- [x] 3.1 [测试] integration：admin block/restore 操作 `users.status`（非 im_users.allowed）；approve/pending 端点移除（404 或不存在）；统一身份视图仍列 im_users 映射（先红）
- [x] 3.2 [实现] im_gateway_management allowlist admin：block/restore → users.status；移除 allowed-based approve/pending/default 逻辑与端点；保留身份视图 → 3.1 转绿

## 4. 文档 + spec 同步

- [x] 4.1 `docs/architecture/data-model.md` §3.2 + ER 图：im_users 去 owner_id/allowed、补 FK user_id→users、UNIQUE 更新；users.status 注记为 IM 封禁机制
- [x] 4.2 archive 时同步 delta：`im-user-mapping`（Schema/uniqueness/map MODIFIED）、`im-user-allowlist`（pending/approve/default REMOVED、block/batch MODIFIED→users.status）

## 5. 收尾

- [x] 5.1 `make test-pr` 全绿；`uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败（重点：IM 身份解析 + edge_tenant provisioning + 封禁强制 + standalone 透传不变）
- [x] 5.2 全仓 grep：无残留 `im_users.owner_id` / `allowed` 读写；`check_allowed_by_user_id` 移除或收口
- [x] 5.3 `openspec validate slim-im-users-to-identity-map` 通过；checkbox 全 `[x]`
