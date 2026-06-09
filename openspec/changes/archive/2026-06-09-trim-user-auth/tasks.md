> chore 减法(移除 invites + 2FA 半成品)。纪律:删除后既有测试**保持全绿**;invites 表迁移**可逆往返**;删代码前**二次 grep 全足迹**;`User`/`_FULL_COLS` 列数同步改、不留解包错位。

## 1. 删除 invites

- [x] 1.1 二次核实:`grep -rn "invite" src tests`,确认生产无路由调用(仅测试 + invite_store 自身)。
- [x] 1.2 写迁移测试(`tests/integration/`):空库 `alembic upgrade head` 后断言 schema 不含 `invites`(它本由 _init_db 运行时建,fresh alembic 库本无此表——断言"不存在")。
- [x] 1.3 新增 Alembic 迁移:`upgrade()` `DROP TABLE IF EXISTS invites`;`downgrade()` 按 `invite_store._init_db` 原 DDL 重建。可逆往返通过。
- [x] 1.4 删除 `src/fleetent/platform/user_management/invite_store.py`。
- [x] 1.5 删除/改写 invite 测试:`tests/integration/test_web_user_mgmt.py`(invite 用例)、`test_user_store.py`(invite_store 引用)。

## 2. 砍 2FA

- [x] 2.1 二次核实:`grep -rn "_enforce_2fa\|totp\|verify_user_2fa\|enable_2fa\|generate_totp\|X-2FA" src tests` 取全足迹。
- [x] 2.2 `user_admin_api.py`:从 6 个高危端点移除 `x_2fa_code` Header 参数 + `_enforce_2fa(...)` 调用;删 `_enforce_2fa` helper。
- [x] 2.3 `auth.py`:删 `generate_totp_secret`/`totp`/`verify_totp`/`enable_2fa`/`verify_user_2fa`。
- [x] 2.4 `user_store.py`:删 `set_totp_secret`;从 `User` dataclass、`_FULL_COLS`、`_init_db` 列定义移除 `totp_secret`(**列数同步、保 SELECT 解包对齐**)。部署库残留列不物理 drop(留 #2)。
- [x] 2.5 删/改 2fa 相关测试。

## 3. spec delta(随归档套用)

- [x] 3.1 确认 `specs/admin-auth/spec.md` REMOVE「2FA for high-risk operations」、`specs/web-user-management/spec.md` REMOVE「One-time invite links」(已写;归档时套用)。

## 4. 收尾验证

- [x] 4.1 `make test-pr` 全绿。
- [x] 4.2 `uv run pytest tests/integration -q` 对照 main 基线无新增失败;**登录/改密/block/建用户/API key 闭环 + 高危 admin 操作(去 2FA 门后仍受 session+role 保护)无回归**。
- [x] 4.3 `openspec validate trim-user-auth` 通过。
- [x] 4.4 复核:`admin-auth` 的「No public self-registration」保留;未碰 OIDC/password 核心流。
