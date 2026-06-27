## 1. DB 迁移（管理库 users 角色值改写）

- [x] 1.1 写测试（红）：integration 测——迁移后 `role='built_in_admin'` 的行全部变为 `role='admin'`,无残留
- [x] 1.2 实现（绿）：新增 Alembic forward-only 迁移 `UPDATE users SET role='admin' WHERE role='built_in_admin'`;**版本号取 apply 时实际 head,不硬编码**;只改数据不改表结构。跑 1.1 见绿

## 2. floor 不变量：user_store 写边界（TDD）

- [x] 2.1 写测试（红）：unit/integration——`_would_orphan_admins`(或等价)逻辑:仅剩一个 active admin 时,降级它/封禁它/删除它/它自我降级 都判为会清零；多 admin 时不拦
- [x] 2.2 实现（绿）：`user_store` 加 floor helper;`set_role`(admin→非admin)、disable/block、delete 三处执行前调用,违反 `raise PermissionError`;**删除** `set_role` 里 built_in_admin 守卫与 `_guard_not_builtin_admin` 的身份判定,改为 floor。跑 2.1 见绿
- [x] 2.3 写测试（红）：integration 经 API——`PATCH /admin/users/{id}/role`、block、delete 对最后一个 active admin 返回 403 且不持久化；多 admin 时提升+自我降级两步成功(转移)
- [x] 2.4 实现（绿）：API 层把 `PermissionError` 转 403(多数端点已如此,补齐 block/delete 路径)。跑 2.3 见绿

## 3. seed 与 bootstrap 识别去角色化（TDD）

- [x] 3.1 写测试（红）：`seed_builtin_admin`——无 active admin 时种子 `role=admin` + must_reset；已有 active admin 时不种(幂等)；零 active admin(全员移除)时 break-glass 重建
- [x] 3.2 实现（绿）：`auth.seed_builtin_admin` 幂等判据改 `count(active admin)==0`,`set_role("admin")`;`get_builtin_admin` 重写为按 `name==BUILTIN_ADMIN_NAME AND email IS NULL` 识别种子账号。跑 3.1 见绿
- [x] 3.3 写测试（红）：用户名 "admin" 登录在去角色化后仍命中种子账号(`user_admin_api.py:97` 路径)；"密码仍默认则再强制 must_reset" 仍生效
- [x] 3.4 实现（绿）：调整 `user_admin_api` 的用户名登录解析走新的 `get_builtin_admin`;保留默认密码再强制 must_reset 逻辑(作用于种子账号)。跑 3.3 见绿

## 4. 清理门常量（批量）

- [x] 4.1 把 14 处 `_ADMIN_ROLES = {"admin","built_in_admin"}` 改为 `{"admin"}`;`server.py:536` 的 `{"admin","built_in_admin"}` 同改;`block_service.py` 的 built_in_admin 判定改为 floor(或移除,统一走 user_store 守卫)
- [x] 4.2 `git grep -n built_in_admin -- src/` 清零(除迁移文件/必要注释);确认无遗漏门

## 5. change 收尾

- [x] 5.1 受影响层:`uv run pytest tests/integration -k "admin or auth or user" -q` 与相关 unit 无新增失败
- [x] 5.2 `make test-pr` + `make test-integration-ci` + `make test-unit-ci`(coverage ≥ 阈值)对照 main 基线无新增失败
- [x] 5.3 本 change 触及文件 `uv run ruff format` / `ruff check` / `mypy src` 全绿
- [x] 5.4 验证基线提醒:本 change 在 platform 内,不影响 `fleetent agent run` 无 platform 基线(无需额外验证,但勿引入 platform→agent 依赖)
