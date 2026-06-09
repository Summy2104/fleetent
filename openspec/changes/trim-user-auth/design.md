## Context

用户/auth 域两处半成品(经核实):**invites**(独立建用户、不发邮件、生产无路由,仅测试调用)与 **2FA**(`_enforce_2fa` step-up 挂 6 个高危 admin 操作,但无 enable/QR/disable/恢复,开不了)。chore 减法,移除二者。当前密码登录闭环(admin 建用户/设密码/login/改密/block/API key)完整,不依赖它们。

## Goals / Non-Goals

**Goals**:删 invites(store+表+测试)+ 砍 2FA(enforce 接线 + totp 函数 + set_totp_secret + 列定义)+ 两条 spec REMOVE。

**Non-Goals**:
- `totp_secret` 列的**物理 drop**——users 表不在 alembic,残留列留 #2 收编时清(本期只从代码 `_init_db`/`_FULL_COLS`/`User` 移除,部署库列保留休眠)。
- 自助注册 / OIDC(本就不做 / 归 #4)。`admin-auth` 的「No public self-registration」保留。

## Decisions

**D1：invites 表用 `DROP TABLE IF EXISTS` 迁移。** invites 是独立整表(由 `invite_store._init_db` 运行时自建、不在 alembic);删 `invite_store.py` 停止建表 + 迁移清部署库残留,downgrade 按原 DDL 重建。（与 descope-quota 同手法。）

**D2：totp_secret 列只从代码移除,不发物理 drop 迁移。** users 表不在 alembic,对它发 alter 迁移与现状不一致;从 `_init_db`/`_FULL_COLS`/`User` 移除即让 fresh 库不再有该列、代码不再引用,部署库残留列休眠无害,物理 drop 随 #2(users 入 alembic)一并做。与 connectors.agent_id 的处理一致。

**D3：2FA 接线干净拆除。** `user_admin_api` 的 6 个高危端点去掉 `X-2FA-Code` Header 参数 + `_enforce_2fa(...)` 调用 + 删 `_enforce_2fa` helper;`auth.py` 删 5 个 totp 函数;`user_store` 删 `set_totp_secret`。

## Risks / Trade-offs

- **[残留引用]** → 删前 grep 全足迹(`_enforce_2fa`/`totp`/`verify_user_2fa`/`enable_2fa`/`X-2FA`/`invite`),含 tests,逐一清。
- **[迁移可逆]** → invites `DROP IF EXISTS` + downgrade 重建;往返通过。
- **[行为回归]** → 无:2FA 本就开不了(无 enable)、invites 本就不可达;高危 admin 操作去掉 2FA 门后仍受 session+role 保护;跑 user_admin 既有测试 + 登录/改密/block 闭环确认无回归。
- **[`User.totp_secret` 移除影响 _FULL_COLS SELECT]** → 同步改 `_FULL_COLS` 与 `User` 字段数,避免列数/解包不匹配;跑 user_store 测试确认。
