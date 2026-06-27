## Why

当前 `built_in_admin` 角色把三件正交的事焊死在一起:① bootstrap 种子身份、② 不可被动(降级/封禁/删除)的保护、③ 与 `admin` 完全相同的权限级别。它本质不是一个"权限层级",而是一个"被特殊对待的具体账号"——保护机制钉死的是**身份**("这个 user 不可动"),而不是**不变量**("系统必须始终有管理员")。这导致管理员是事实上的单点、权限无法自然转移。

经讨论决定:**砍掉 `built_in_admin` 这一层,只保留 `admin` / `viewer` 两级**;把"身份神圣"换成"数量下限"——`admin` 可多人持有、可自由转移,但系统保证**至少始终有一个 active admin**。bootstrap 种子账号只是"第一个 admin",与后来提升的 admin 完全平权。

## What Changes

- **角色二级化**:移除 `built_in_admin` 角色,角色只剩 `admin` / `viewer`(+ 正交的 `service`)。`is_admin` 兼容语义改为 `role == "admin"`。
- **保护从身份改为数量下限(floor ≥ 1)**:任何操作 MUST NOT 使 `count(role=admin AND status=active)` 降到 0。具体拦截**降级 / 封禁 / 删除 / 自我降级或自我封禁**最后一个 active admin,违反返回 403 + 明确错误。
- **admin 多人 + 可转移**:任意多个 admin;转移 = 提升他人为 admin + 自我降级(下限保护下自然实现,无需专门机制)。
- **seed 改为 floor 恢复语义**:启动时若**不存在 active admin** 则种子 admin/admin + `must_reset`(同时兼作 break-glass:全员丢失时自动重建)。种子账号 `role=admin`。
- **bootstrap 识别去角色化**:`get_builtin_admin()` 不再靠 `role='built_in_admin'` 识别种子账号(角色已合并);改为按种子账号特征(name=固定用户名 且 email 为空)识别,用于"用户名 `admin` 登录"与 seed 幂等(详见 design)。
- **清理 14 处门常量**:各 `*_admin_api.py` 的 `_ADMIN_ROLES = {"admin", "built_in_admin"}` → `{"admin"}`。
- **DB 迁移**:管理库 `users` 中现存 `role='built_in_admin'` 行迁移为 `role='admin'`(Alembic,forward-only)。

**保持不动**(已与用户确认):bootstrap 那套 admin/admin + `must_reset` + "密码仍是默认值则启动时再强制 reset" 的安全闸不变;`service` principal 不可提为人类角色不变。

## Capabilities

### New Capabilities
<!-- 无新增能力。 -->

### Modified Capabilities
- `admin-auth`: 角色模型由三级改为二级(移除 `built_in_admin`);管理员保护由"身份不可动"改为"active admin 数量下限 ≥ 1";seed 改为"无 active admin 时种子/恢复";admin 多人持有且可转移。涉及 MODIFIED 现有 `Three-tier roles` / `Built-in admin seeding` / `Built-in admin is protected` 三条 requirement + 新增"admin 可多持有与转移"约束。

## Impact

- **owning package**: `platform`(用户/认证)+ 顶层 `auth.py`、`user_store.py`、`server.py`。
- **public API surface**: 无新增端点;`PATCH /admin/users/{id}/role`、block、delete 的拒绝条件改变(由"是否 built_in_admin"改为"是否最后一个 active admin")。
- **owned tables**: `users`(管理库,Alembic)——新增一条 forward-only 数据迁移把 `built_in_admin` 值改写为 `admin`,不改表结构。
- **config namespace**: 无。
- **cross-module dependencies**: 无新增;纯 platform + 顶层 auth/store 内;不触碰 agent/platform 解耦铁律。**广度提示**:约 14 个 `*_admin_api.py` 的 `_ADMIN_ROLES` 常量需同步从 `{"admin","built_in_admin"}` 收为 `{"admin"}`(机械改动,但面广)。
- **migration / shim plan**: Alembic 数据迁移(值改写);`built_in_admin` 角色值彻底退场,无需保留 shim(无外部依赖该字符串)。floor 检查集中在 `user_store` 写边界,避免散落。
- **测试**:floor 不变量(降级/封禁/删除/自我操作最后一个 admin 全拦)、多 admin 转移、seed 在无 active admin 时恢复、用户名 admin 登录在去角色化后仍可用、迁移正确性——以 integration 为主;floor 纯判断逻辑可 unit。
