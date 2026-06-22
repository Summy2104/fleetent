## Why

无 verified email 的渠道（Telegram/WhatsApp）无法自动并号（#2 的 email-join 用不上）——它们首次接触建的是**渠道独立 user**。要把这种渠道身份和某真人的 email-keyed 身份并成一个人，需要**手动 `/link`（双向控制）**：已登录（经 #1 OIDC）的用户发起、从目标渠道账号回发一次性 code、平台据此绑定。这是车道 D 最后一块（见 `docs/architecture/identity-channel-ingress.md` §2.3）。

依赖均已落地：#1(OIDC web 登录提供已认证发起方)、#2(`_attach_identity`/im_users 并号)、#4a(node IM-edge + node→platform 端点模式)。

## What Changes

- **web 发起 link（平台，OIDC session 认证）**：已登录用户请求"绑定某渠道" → 平台签发**一次性 code** + 存 pending-link `{code → user_id, tenant, TTL}`。
- **node IM-edge 截 `/link <code>`**：node 的 IM-edge 识别 `/link <code>` 命令（不走 agent normalizer，因绑定是平台侧）→ 调 `POST /nodes/{node_id}/link-confirm`（node→platform，node-key 鉴权）带 `(platform, platform_user_id, code)`。
- **平台 link-confirm**：校验 code（pending-link、未过期）→ 若该 `(platform, platform_user_id)` **尚无映射** → `_attach_identity` 到 code 对应的 user_id → **写审计**。**attach-only**（与 #2 一致）：若渠道身份已映射到别的 user，**不合并**、拒并提示。
- **unlink（可逆）**：用户自助 / admin 解绑某渠道映射 → 删 im_users 行 + **审计**；该渠道未来消息回落独立身份（`resolve_or_provision` 重新建/解析）。
- **错绑数据不自动迁移**（决策已定）：unlink 只改未来解析；错绑窗口期落在错 user_id 名下的数据**留痕、admin 手动清理**（自动重归属 post-v1）。

### 不在本切片
- 自动重归属错绑数据（post-v1）；per-tenant IdP；有 email 渠道的自动并号（#2 已做）。

## Capabilities

### Modified Capabilities
- `im-user-mapping`: 新增**手动渠道绑定/解绑**——无 email 渠道经双向控制 `/link`（web 发起出 code、目标渠道回发 code）attach-only 绑到 email-keyed user；unlink 可逆；link/unlink 全程审计；错绑数据不自动迁移。
- `platform-agent-gateway`: node IM-edge 识别 `/link <code>` → 经 `POST /nodes/{node_id}/link-confirm`（node-key）让平台校验 code + 绑定（绑定恒平台侧，agent 不参与）。

## Impact

- **owning packages**：`platform`（link-initiate + unlink 端点[OIDC session 认证]、`node_desired_state_api` 加 link-confirm[node-key]、pending-link 存储、调 `_attach_identity` + audit）；`node`（`im_edge.py` 截 `/link` → 调 link-confirm）；`im_gateway`（`/link` 命令识别，node 宿主）
- **public API surface**：web `POST .../link/initiate`(出 code) + `POST .../link/unlink`（OIDC session）；node `POST /nodes/{node_id}/link-confirm`（node-key）
- **owned tables**：`im_users`（link 加行经 `_attach_identity`、unlink 删行——现成表）；pending-link = **transient**（内存/短 TTL，仿 session，不建表）；审计走现有 `audit_log`
- **config namespace**：无（code TTL 可常量/复用配置）
- **cross-module dependencies**：node→platform（link-confirm，node-key 既有通道）；平台用 #2 的 `_attach_identity`；im_gateway 仍不 import platform；无 agent→platform
- **migration / shim**：无 schema/迁移（im_users 现成；pending-link 不落库）
- **验证基线**：不影响 standalone（`/link` 是 managed 多渠道并号能力；standalone 单渠道无需）
- 与车道 A（governance）/ KB（① scheduler）零重叠；当前无在飞窗口
