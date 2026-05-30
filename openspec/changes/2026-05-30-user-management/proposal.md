## Why

平台的用户管理目前只够 MVP：`user_store` 一个用户一把 API key、CLI 建账、`im_user_store` 默认拒绝直到 admin approve。缺口对照 `platform.md` 的 Admin 后台设计：

1. **没有 web 身份与登录**：用户没有邮箱/密码、没有角色，后台无法登录，更没有"内置管理员"。`agent-admin-api` 临时引入的布尔 `is_admin` 不足以表达 admin / viewer / 内置 admin 三级。
2. **建账只有 CLI**：无法在后台手动建账、发邀请链接、CSV 批量导入；也没有"禁止公网自助注册"的明确约束。
3. **单 API key**：一个用户只能有一把 key，无法为 CI/CD 单独签发、无法设有效期 / agent 级 scope、无法独立轮换/撤销、看不到使用情况。
4. **拉黑不级联、无审计**：没有"一键拉黑→失效所有 key + 封 IM + 禁重复注册"的级联，也没有统一审计日志。
5. **IM 用户默认拒**：`platform.md` v1.0 要求**默认放行**（由 channel 白名单准入），工作台聚焦加黑维护，且加黑仅 admin；当前实现是默认 `allowed=0` 逐个 approve。
6. **无配额**：无法对 per-user / 全局设 token / 调用次数上限。

本 change 把这些补齐为一个完整的用户 / IM 用户管理底座。

## What Changes

**ADDED**
- `admin-auth`：内置 admin 种子化（固定用户名 + 临时密码 + `must_reset`，首登强制改密、不可删/改名/降级）；邮箱+密码登录；三级角色 `built_in_admin` / `admin` / `viewer`；高危操作 2FA；登录会话空闲超时；`/admin/*` 按角色守卫。
- `web-user-management`：admin 在后台手动建账（邮箱/姓名/初始密码或首登自设）、一次性邀请链接、CSV 批量导入；用户列表（按状态/最近活跃/绑定 IM 数筛排）与生命周期（编辑/禁用/删除）；**无公网自助注册入口**。
- `api-key-management`：一个用户多把 key，每把可设有效期、**agent 级 scope 白名单**、备注；独立新增/轮换/撤销互不影响；使用情况（创建/最后使用/来源 IP·UA/累计调用）；过期前提醒与一键续期。
- `user-blocklist`：一键拉黑级联（撤销全部 key + 同步封禁关联 IM + 邮箱/subject 进禁注册名单 + 写审计）；批量拉黑；解封后 key 不自动复活、IM 需重新审批。
- `usage-quota`：per-user 与全局的 token / 调用次数上限；超限 `/chat` 返回 429 并发事件。
- `platform-audit-log`：所有平台管理动作（建删用户、轮换/撤销 key、加黑/恢复 IM、改角色、改配额）记录"谁/何时/对什么资源/做了什么"，可检索可导出；删除/撤销/批量封禁等高危动作要求二次确认。

**MODIFIED**
- `user-store`：`users` 表加 `email` / `password_hash` / `role` / `status`(active/disabled/blocked) / `must_reset`；API key 从 `users.api_key` 单列迁到独立 `api_keys` 表（多 key + scope + 有效期 + 使用统计）；`get_by_api_key` 改查 `api_keys` 并校验有效期/撤销/拉黑。
- `im-user-allowlist`：新 IM 用户**默认放行**（准入交给 `im-channel-allowlist`），`get_or_create` 默认 `allowed=1`；工作台聚焦加黑/恢复（仅 admin），支持批量；多平台 IM 账号合并到同一内部 User；CLI `block-user` 收回（deprecated 提示），加黑/恢复改后台。

## Capabilities

### New Capabilities

- `admin-auth`
- `web-user-management`
- `api-key-management`
- `user-blocklist`
- `usage-quota`
- `platform-audit-log`

### Modified Capabilities

- `user-store`
- `im-user-allowlist`

## Impact

- **代码**：
  - 新增：`auth.py`（密码哈希、登录会话、2FA、角色守卫、内置 admin 种子）、`user_admin_api.py`（`/admin/users`、`/admin/im-users`、`/admin/audit` 路由）、`api_key_store.py`（`api_keys` 表）、`invite_store.py`（邀请 token）、`audit_log.py`（审计写/查）、`quota.py`（配额检查）
  - 修改：`user_store.py`（users 多列 + 改 get_by_api_key 走 api_keys）、`im_user_store.py`（默认放行 + 批量加黑/恢复 + 合并视图）、`server.py`（mount router、`/chat` 加配额检查、key 使用情况记录）、`admin.py`（CLI：种子内置 admin、deprecate block-user）、`agent_policy.py` 复用（key scope 用 fnmatch 同款）
- **依赖**：需要密码哈希（用标准库 `hashlib.scrypt` 或引入 `argon2-cffi` / `bcrypt`，PR 中定）；2FA 用 TOTP（标准库可实现 HOTP/TOTP 或引入 `pyotp`）。两项为可能的新依赖，按"新依赖必须讨论"在 PR 说明，倾向先用标准库实现避免引入。
- **数据**：`users` 加列；新增 `api_keys` / `invites` / `audit_log` / `blocked_registrations` / `quotas` 表；`im_users` 默认 `allowed=1`（迁移：存量保持原值，新建默认放行）。
- **认证依赖与取代**：本 change 的 `admin-auth` 以 `role` 列**取代** `agent-admin-api` 的布尔 `is_admin`；提供兼容映射（`is_admin == role in {admin, built_in_admin}`），`/admin/*` 守卫统一走角色。
- **破坏性**：
  - `users.api_key` 单列废弃，迁移到 `api_keys` 表（一次性迁移脚本把现有 key 搬过去，scope 默认 `*`、无过期）。
  - 现直接读 `users.api_key` 的代码需改读 `api_keys`。
  - IM 默认放行翻转：部署方若依赖"默认拒"，需开启对应 channel 白名单的 `allowlist_enforced`。

## Commit 切分建议

每个 commit 自包含、内部 TDD（测试先红 → 实现 → 绿）：

1. `feat(user_store): users role/status/email/password + migration`（1.x）
2. `feat(api_key_store): api_keys table + scope + usage + expiry`（2.x）
3. `refactor(user_store): get_by_api_key resolves via api_keys with validity checks`（3.x）
4. `feat(auth): password hashing, login sessions, role guard, built-in admin seed`（4.x）
5. `feat(auth): 2FA + idle timeout`（5.x）
6. `feat(web_user_mgmt): admin create / invite / CSV / lifecycle`（6.x）
7. `feat(user_blocklist): cascade block/unblock + batch + dedup`（7.x）
8. `feat(im_user): default-allow flip + block/restore workbench + batch`（8.x）
9. `feat(usage_quota): per-user/global limits + 429`（9.x）
10. `feat(audit_log): write + search/export + high-risk confirm`（10.x）
11. `feat(user_admin_api): /admin/users + /admin/im-users + /admin/audit`（11.x）
12. `feat(admin): seed built-in admin CLI + deprecate block-user`（12.x）
