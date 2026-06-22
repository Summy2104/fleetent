## Context

- 绑定原语现成：`im_gateway_management/identity.py::_attach_identity(platform, platform_user_id, user_id)`（:74）；`_get_mapped_user`（:60）查现有；`disable_im_accounts`（:193）。缺**单条 unlink**。
- 命令处理在 normalizer（agent 侧 `/user /clear` + approval 命令）；但绑定是平台侧写 → `/link` 不能走 agent normalizer，须在 **node IM-edge** 截。
- node→platform 端点模式现成：`node_desired_state_api`（`/nodes` 前缀、node-key）已有 `POST /nodes/{id}/identity/resolve`（#4a）。
- 审计：`audit_log`（顶层，governance/audit_log 是 shim）。
- OIDC session（#1）提供已认证发起方。

## Goals / Non-Goals

**Goals:**
- 无 email 渠道经双向控制 `/link` attach 到 email-keyed user；可逆 unlink + 审计。
- 绑定恒平台侧；agent 不参与；node IM-edge 截 `/link` → 平台 confirm。
- 错绑数据不自动迁移。

**Non-Goals:**
- 自动重归属（post-v1）；per-tenant IdP；有 email 自动并号（#2）。

## Decisions

- **D1 · code 方向 = web 发起（路径 A）**：已登录（OIDC）用户在 web `link/initiate` 拿一次性 code → 从目标渠道回发 `/link <code>`。web 是已认证锚点，最稳。（路径 B 渠道发起为备选，不做。）
- **D2 · pending-link 临时态**：`{code → (user_id, tenant), expires_at}`，短 TTL（如 10min），内存/单进程平台态（仿现有 session）。不建表。
- **D3 · node IM-edge 截 `/link <code>`** → `POST /nodes/{node_id}/link-confirm`（node-key）带 `(platform, platform_user_id, code)`。平台校验 code（存在/未过期）→ `_get_mapped_user` 查该渠道身份是否已映射：未映射→`_attach_identity(...,pending.user_id)`+审计；已映射别的 user→拒（attach-only，不合并）。
- **D4 · unlink**：web/admin 端点（OIDC/admin session）→ 删该 `(platform, platform_user_id)` im_users 行（新增 store helper `unlink_identity`）+ 审计。错绑数据不自动迁移。
- **D5 · 审计**：link/unlink 走 `audit_log.write_audit`（actor、两身份、time、code 来源）。

## Risks / Trade-offs

- **绑定恒平台、`/link` 不能进 agent**：node IM-edge 必须在转发给 agent normalizer **之前**拦截 `/link`（否则它会被当普通消息进 loop）。注意拦截顺序。
- **code 安全**：一次性、短 TTL、用后即焚；node→platform confirm 用 node-key（既有通道）。code 泄漏窗口小（短 TTL + 单次）。
- **attach-only 不合并**：已映射渠道身份提交他人 code → 拒，不改挂（防误并/接管）。测试覆盖。
- **pending-link 内存态多 worker/重启**：单进程平台 OK；若多 worker 需共享态（与现有 session 同限，本切片沿用现状）。
- **standalone 不受影响**：`/link` 是 managed 多渠道并号能力；standalone 单渠道用不到，不破坏 `fleetent agent run`。
