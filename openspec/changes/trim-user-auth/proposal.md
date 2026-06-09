## Why

用户/auth 域有两处"建了没接线/半成品",v1 descope:

- **invites**:独立的自助密码注册路径——`accept_invite` 自己建用户(不依赖 admin 预建)、**不发邮件**(只吐 token,送达没人管)、**生产无任何路由**(create/accept 仅测试调用,不可达),且与"admin 建用户 + admin 设密码"功能重叠。
- **2FA(TOTP)**:`_enforce_2fa` 的 step-up 校验已挂在 6 个高危 admin 操作上,但**无 enable 端点、无 otpauth/QR 设置、无 disable、无丢失恢复**——用户**根本开不了**,实际用不上。

v1 用户/auth 闭环(admin 建用户/设密码/`/login`+session/改密/block/API key)**完整、不依赖这两者**。要自助注册/强制 2FA 时再整体重做(自助注册依赖邮件 infra;2FA 要补 enable+QR+disable+恢复)。

## What Changes

- **删 invites**:`invite_store.py` + `invites` 表(`DROP TABLE IF EXISTS` 迁移,downgrade 重建)+ 相关测试。
- **砍 2FA**:移除 `user_admin_api` 的 `_enforce_2fa` + 6 处 `X-2FA-Code` 接线;删 `auth.py` 的 `generate_totp_secret`/`totp`/`verify_totp`/`enable_2fa`/`verify_user_2fa`;删 `user_store.set_totp_secret`,并从 `User`/`_FULL_COLS`/`_init_db` 移除 `totp_secret`。
- **specs**:REMOVE `admin-auth` 的「2FA for high-risk operations」+ `web-user-management` 的「One-time invite links」。

> 不做:`totp_secret` 列的**物理 drop**(users 表不在 alembic,部署库残留列留 #2 管理表收编时清);自助注册/OIDC(本就不做 / 归 #4)。`admin-auth` 的「No public self-registration」**保留**(与 v1 纯 admin 一致)。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `admin-auth`: 移除「2FA for high-risk operations」requirement(登录/seeding/首登改密/角色/无自助注册等保留)。
- `web-user-management`: 移除「One-time invite links」requirement(admin 手动建用户/用户列表与生命周期/CSV 导入保留)。

## Impact

- **代码**:删 `platform/user_management/invite_store.py`;`user_admin_api.py`(去 `_enforce_2fa` + 6 处 `X-2FA-Code` Header/调用);`auth.py`(去 5 个 totp 函数);`user_store.py`(去 `set_totp_secret` + `User.totp_secret` + `_FULL_COLS`/`_init_db` 的列)。
- **迁移**:`DROP TABLE IF EXISTS invites`(downgrade 重建)。`totp_secret` 列物理 drop 留 #2。
- **specs**:`admin-auth` / `web-user-management` 各 REMOVE 一条。
- **测试**:删/改 `tests/integration/test_web_user_mgmt.py`(invite + 2fa 部分)、`test_user_store.py`(invite 引用)。
- **零影响**:密码登录/session/改密/block/API key 闭环不变(2FA 本就开不了、invites 本就不可达)。
