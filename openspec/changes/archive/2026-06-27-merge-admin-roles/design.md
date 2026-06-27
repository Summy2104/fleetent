## Context

`built_in_admin` 现状(已核实触点):
- 角色值散落 ~16 文件:14 处 `_ADMIN_ROLES = {"admin","built_in_admin"}` 门常量(各 `*_admin_api.py`)、`server.py:536` has_role 检查。
- `auth.py`:`seed_builtin_admin()` 首启种 `admin/admin` + `must_reset` + `set_role("built_in_admin")`;再启时若密码仍为默认则重置 must_reset。
- `user_store.py`:`get_builtin_admin()`(`SELECT ... WHERE role='built_in_admin'`)、`set_role` 的"built_in_admin 不可降级"守卫、`_guard_not_builtin_admin`(disable/delete 守卫)。
- `block_service.py:24`:封禁守卫。
- `user_admin_api.py:97`:登录时 identifier == 固定用户名 "admin" → `get_builtin_admin()`(种子账号无 email,靠用户名登录)。

诊断:`built_in_admin` 把 ①bootstrap 身份 ②保护 ③权限级别 三者焊死。本 change 拆开:③→并入 `admin`;②→改为 active admin 数量下限;①→若仍需识别种子账号,用非角色特征表达。

## Goals / Non-Goals

**Goals:**
- 角色二级(admin/viewer);移除 `built_in_admin`。
- 管理员保护 = active admin 数量下限 ≥ 1(身份无关)。
- admin 多人持有、可自由转移。
- floor 检查集中在 `user_store` 写边界,不散落到各 API。

**Non-Goals:**
- 不引入"super admin"第四层 / 权限差(已决定不做)。
- 不改 bootstrap 的 admin/admin + must_reset + 默认值再强制那套安全闸。
- 不动 `service` principal 不可提权的正交护栏。
- 不引入按域/租户的管理员范围(全局 admin)。

## Decisions

**D1 — 保护逻辑统一为 `user_store` 写边界的 floor 检查。** 新增内部 helper(如 `_would_orphan_admins(target_user_id, *, after_role=None, after_status=None) -> bool`):计算"若对 target 施加该变更后,是否 `count(role=admin AND status=active) == 0`"。`set_role`(admin→非 admin)、block/disable、delete 三处在执行前调用它,真则 `raise PermissionError`(API 层转 403)。理由:与现有 `_guard_not_builtin_admin` 同址同模式,集中可审计;避免每个 `*_admin_api` 各判一次。自我操作天然被覆盖(target 是自己且自己是最后一个 → 拦)。

**D2 — bootstrap 身份去角色化:用 name + 无 email 识别,不新增列。** 种子账号特征 = `name == BUILTIN_ADMIN_NAME("admin") AND email IS NULL`。`get_builtin_admin()` 重写为按此特征查(仍限 role=admin)。用途仅二:① `user_admin_api.py:97` 的"用户名 admin 登录"(种子账号无 email,需用户名登入);② seed 幂等的"是否已有种子账号"判断。备选(加 `is_bootstrap` 布尔列)被否:多一列 schema 改动、收益低;name+无email 足以唯一标识种子账号(人类创建的 admin 都带 email)。**风险点**:若运营给种子账号补了 email,则"用户名 admin 登录"失效——可接受(补了 email 就用 email 登录,更规范),在文档注明。

**D3 — seed 语义从"无 built_in_admin"改为"无 active admin"。** `seed_builtin_admin()` 幂等判据改为 `count(active admin) == 0` 才种;天然兼作 break-glass(全员丢失自动重建)。种子 `role=admin`。"密码仍默认则再强制 must_reset"的逻辑保留,作用对象为种子账号(经 D2 识别)。

**D4 — `_ADMIN_ROLES` 收为 `{"admin"}`,机械批改 14 处。** 迁移已把所有 `built_in_admin` 行改成 `admin`,集合里留 `built_in_admin` 只是死值;一并清掉保持整洁。需确保**无遗漏**(留一处旧门会让迁移后的 admin 仍被放行——巧合正确,但语义脏)。用 grep 核对清零。

**D5 — Alembic forward-only 数据迁移。** `UPDATE users SET role='admin' WHERE role='built_in_admin'`。**迁移版本号不硬编码**——以 apply 时的实际 head 为准(并行 change 可能占号,撞号在 merge 时刻才暴露)。仅数据、不改表结构。

## Risks / Trade-offs

- **[floor 检查遗漏某条减员路径 → 可能锁死全员] → Mitigation**:集中在 user_store 的 set_role/block/delete 三个写函数;integration 测显式覆盖四种(降级/封禁/删除/自我)对"最后一个 admin"的拦截。
- **[14 处门常量漏改一处] → Mitigation**:迁移后漏改的门是 `{"admin","built_in_admin"}`,因无 built_in_admin 行而行为正确,但语义脏;收尾 `git grep built_in_admin -- src/` 必须清零(除测试/迁移注释)。
- **[种子账号被补 email 后用户名登录失效] → Mitigation**:文档说明;补 email 后改用 email 登录(更规范)。
- **[迁移与并行 change 撞 Alembic 号] → Mitigation**:apply 时取实际 head、merge 后自检单 head(见 apply 闭环)。
- **[已有部署存在多个历史 built_in_admin?] → Mitigation**:历史上 seed 只造一个,但迁移用 `WHERE role='built_in_admin'` 全量改写,多个也安全收敛为 admin。

## Migration Plan

1. Alembic 数据迁移:`built_in_admin` → `admin`。
2. `user_store`:重写 `get_builtin_admin`(name+无email)、`set_role` 去掉 built_in_admin 守卫加 floor、block/delete 守卫改 floor。
3. `auth.seed_builtin_admin`:幂等判据改 `count(active admin)==0`,`set_role("admin")`。
4. 批改 14 处 `_ADMIN_ROLES` + `server.py` has_role → `{"admin"}` / `=="admin"`。
5. 回滚:代码 `git revert`;数据迁移为 forward-only,回滚后 `admin` 行不会自动变回 `built_in_admin`,但二级模型下 `admin` 即正确角色,无功能影响(原 built_in_admin 的保护由 floor 提供)。

## Open Questions

- 无。bootstrap 识别(D2)、seed 语义(D3)、floor 落点(D1)均已定。
