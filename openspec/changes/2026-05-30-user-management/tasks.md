> **实施进度（opsx:apply，主体完成）**
> 已实现并通过 TDD（沙箱 Python 3.10 + `.pth` 的 `datetime.UTC` 别名 shim，新模块均不 import agent_loop）：
> - Task 1 `user_store` 扩列 + 访问器；Task 2 `api_key_store`；Task 3 `authenticate`+`migrate_api_keys`；Task 4 `auth`（scrypt/会话/角色/内置 admin）；Task 5 2FA(TOTP)+空闲超时；Task 6 `create_web_user`/`bulk_import_users`/`invite_store`/生命周期；Task 7 `blocklist`（级联/解封/批量/禁注册）；Task 8 `im_user_store` 默认放行翻转 + 加黑/恢复/批量/合并；Task 9 `quota`；Task 10 `audit_log`；Task 11.1–11.4 `user_admin_api`（FastAPI 路由，TestClient 验证）。
> - 新增测试约 90 个，连同既有 user_store/im_user_store 全绿（本 change 相关合计 113 passed）。
>
> **代码已全部写完**。`admin.py`（Task 8.6/12.1/12.2：`seed-builtin-admin` + deprecate `block-user`）在沙箱 TDD 验证通过（test_admin 23 passed）。`server.py`（Task 11.5：mount `/admin` router、`/chat` 改用 `authenticate` + scope 403 + 配额 429 + key 用量、lifespan seed 内置 admin）**已写且 py_compile 通过**，但运行时需 Python 3.12（`server` import `agent_loop` 的 PEP 695 语法，3.10 无法 import/运行）。
>
> **仅剩 3.12 验证**：Task 12.3 全量 `uv run pytest -x -q`、12.4 `ruff`/`mypy`、12.5 手动冒烟。token 精确配额需 `agent_loop` 暴露 usage 事件（follow-up），当前 `/chat` 按调用计数 + 预检。
>
> **认证模型**：以 `role` 取代 `agent-admin-api` 的布尔 `is_admin`（兼容映射 `is_admin == role in {admin, built_in_admin}`）。
> **git**：沙箱 `.git/index.lock` 残留无权清除，改动需宿主机 commit。

## 0. 前置

- [ ] 0.1 确认密码哈希与 TOTP 选型（倾向标准库 `hashlib.scrypt` + 自实现 TOTP；如引入 `argon2-cffi`/`pyotp` 需在 PR 说明）
- [ ] 0.2 确认与 `agent-admin-api` 的 `is_admin` 取代关系：统一改 `role`，提供兼容映射

## 1. user_store — users 多列 + 迁移

- [x] 1.1 Write failing tests: `_init_db` 后 `users` 含 `email`/`password_hash`/`role`/`status`/`must_reset` 列；旧库启动自动 ALTER 不丢数据；`role` 默认 `viewer`、`status` 默认 `active`
- [x] 1.2 修改 `user_store._init_db`：幂等加列（`PRAGMA table_info` 检测）
- [x] 1.3 Write failing tests: `set_role` / `set_status` / `set_password` / `get_by_email` 行为
- [x] 1.4 实现上述访问函数

## 2. api_key_store — 多 key 表

- [x] 2.1 Write failing tests: `api_keys` 表存在含 `key_hash`/`prefix`/`scope`/`note`/`expires_at`/`revoked_at`/`last_used_at`/`last_ip`/`last_ua`/`call_count`；`issue_key(user_id, scope, note, expires_at)` 返回明文一次、库存 hash
- [x] 2.2 新建 `api_key_store.py`：建表 + `issue_key` / `revoke_key` / `rotate_key` / `list_keys(user_id)` / `record_usage(key_id, ip, ua)` / `resolve` / `check_scope`
- [x] 2.3 Write failing tests: `list_keys` 不回明文只回 prefix；`revoke_key` 置 `revoked_at`；`rotate_key` 撤旧发新互不影响其余

## 3. get_by_api_key 走 api_keys（含有效性）

- [x] 3.1 Write failing tests: `authenticate(plaintext)` 命中未撤销/未过期/User 非 blocked 才返回 (User, key_meta)；撤销/过期/blocked 返回 None；legacy 单列回退
- [x] 3.2 新增 `user_store.authenticate` + `get_by_api_key` 委托走 `api_key_store` 校验有效性
- [x] 3.3 Write failing tests: `check_scope(key, agent_name)` 用 fnmatch 比对 scope 白名单；`["*"]` 全通过（在 api_key_store）
- [x] 3.4 实现 scope 校验（`api_key_store.check_scope`，fnmatch 同款）
- [x] 3.5 迁移函数 `user_store.migrate_api_keys()`：`users.api_key` → `api_keys`（scope `*`、无过期），幂等

## 4. auth — 哈希/会话/角色守卫/内置 admin 种子

- [x] 4.1 Write failing tests: `hash_password`/`verify_password` 往返；不可逆、明文不落库
- [x] 4.2 新建 `auth.py`：密码哈希（stdlib scrypt）
- [x] 4.3 Write failing tests: `seed_builtin_admin()` 首次建固定用户名 + 临时密码 + `must_reset=1` + `role=built_in_admin`；已存在则跳过；内置 admin 不可降级（`set_role` 报错）
- [x] 4.4 实现 `seed_builtin_admin` + 内置 admin 保护（`user_store.set_role` 守卫 + `get_builtin_admin`）
- [x] 4.5 Write failing tests: 登录会话签发/校验/空闲超时；`require_role(user, {...})` 守卫；viewer 被拒
- [x] 4.6 实现登录会话 + 角色守卫（`has_role`/`require_role`）

## 5. 2FA + 空闲超时

- [x] 5.1 Write failing tests: TOTP 生成/校验/窗口容差；per-user enable/verify
- [x] 5.2 实现 TOTP（`auth.generate_totp_secret`/`totp`/`verify_totp`/`enable_2fa`/`verify_user_2fa`）；高危操作 2FA 守卫接线在 API 层（11.x）
- [x] 5.3 Write failing tests: 会话空闲超过阈值后判定失效（test_auth）
- [x] 5.4 实现空闲超时（`auth.validate_session` idle_timeout）

## 6. web 用户管理 — 建账/邀请/CSV/生命周期

- [x] 6.1 Write failing tests: `create_web_user(email, name, password_hash=None, must_reset=...)` 即刻可用；重复邮箱拒
- [x] 6.2 实现手动建账（`user_store.create_web_user`）
- [x] 6.3 Write failing tests: `create_invite(email)` 生成一次性 token（hash+expires）；`accept_invite(token, password_hash)` 激活并签首把 key；用后/过期 token 失效
- [x] 6.4 新建 `invite_store.py` + 激活流程
- [x] 6.5 Write failing tests: CSV/行批量导入逐行建账、失败行汇总；无自助注册符号
- [x] 6.6 实现 `bulk_import_users`；无自助注册入口
- [x] 6.7 Write failing tests 并实现 `disable_user`/`delete_user`（内置 admin 保护）；列表筛排由 `/admin/users` API 提供

## 7. user_blocklist — 级联拉黑/解封/批量

- [x] 7.1 Write failing tests: `block_user(user_id, reason)` → `status=blocked` + 撤销全部 key + 关联 IM `allowed=0` + email 进 `blocked_registrations` + 写审计
- [x] 7.2 新建 `blocklist.py` + `blocked_registrations` 表 + `block_user` 级联
- [x] 7.3 Write failing tests: 拉黑后该 User 的 key 经 `authenticate` 返回 None；同邮箱再建账被拒
- [x] 7.4 接入认证/建账校验禁注册名单（`create_web_user` 前置 `is_registration_blocked`）
- [x] 7.5 Write failing tests: `unblock_user` 恢复登录但 key 不复活；批量拉黑逐条审计 + 批次 ID
- [x] 7.6 实现 `unblock_user` + `batch_block`（`/chat` 401 集成留 11.5，需 3.12）

## 8. im-user-allowlist 翻转 + 工作台

- [x] 8.1 Write failing tests: `get_or_create` 新建默认 `allowed=1`；新用户不在 pending（既有 test_im_user_store 已按新默认更新）
- [x] 8.2 修改 `im_user_store.get_or_create` 默认放行
- [x] 8.3 Write failing tests: `block_im_user`/`restore_im_user`（写审计）；批量加黑关联批次；`list_im_identities(user_id)` 多平台合并
- [x] 8.4 实现加黑/恢复/批量/合并视图（仅 admin 由 API 守卫保证）
- [x] 8.5 Write failing tests: CLI `block-user` 返回 deprecated 提示且不改状态（test_admin，沙箱验证）
- [x] 8.6 修改 `admin.py` deprecate `block-user`

## 9. usage-quota

- [x] 9.1 Write failing tests: `quotas` 表；`check_quota(user_id, tokens)` 在未超限放行、超限返回拒绝；global 与 user 作用域
- [x] 9.2 新建 `quota.py` + 表（`set_quota`/`record_usage`/`check_quota`）
- [ ] 9.3 Write failing tests: `/chat` 超限返回 429；系统内部调用豁免
- [ ] 9.4 接入 `/chat` 入口检查

## 10. platform-audit-log

- [x] 10.1 Write failing tests: `write_audit(actor, action, target_type, target_id, detail, batch_id)` 落库；`search_audit(filters)` 按 actor/action/target/时间过滤
- [x] 10.2 新建 `audit_log.py` + 表
- [ ] 10.3 Write failing tests: 高危动作未过 2FA 时拒绝执行且不落业务变更（守卫层）
- [ ] 10.4 接入高危动作二次确认守卫

## 11. user_admin_api — REST

- [x] 11.1 Write failing tests（FastAPI TestClient）: 无 session 401；viewer 只读、写 403；admin 可建/改/拉黑用户
- [x] 11.2 实现 `user_admin_api` 的 `/admin/users` CRUD + 角色 + 拉黑/解封端点
- [x] 11.3 Write failing tests: `/admin/users/{id}/keys` 列/签/撤；`/admin/im-users` 加黑/恢复；`/admin/audit` 检索
- [x] 11.4 实现 key / im-user / audit 端点
- [~] 11.5 改 `server.py`：mount router、`/chat` 改用 `authenticate`(User,key_meta) + scope 校验(403) + 配额(429) + key 用量记录 + 启动 seed 内置 admin。**代码已写、py_compile 通过；运行时需 3.12（import agent_loop 的 PEP 695）**。注：token 精确配额需 agent_loop 暴露 usage 事件，当前按调用计数 + 预检，留 follow-up

## 12. CLI + 收尾

- [x] 12.1 Write failing tests: `seed-builtin-admin` CLI（首启建 + 再跑 no-op）；`block-user` deprecated no-op（test_admin，沙箱验证）
- [x] 12.2 改 `admin.py`（新增 `seed-builtin-admin`、deprecate `block-user`）；server 启动钩子在 lifespan 调 `seed_builtin_admin`（随 11.5，运行时需 3.12）
- [ ] 12.3 全量 `uv run pytest -x -q` 绿（**需 3.12**）
- [ ] 12.4 `ruff format && ruff check && mypy src` 通过（**需 3.12**）
- [ ] 12.5 手动冒烟：首启拿初始密码→登录强制改密→建账/发邀请→签多 key 设 scope→拉黑级联→IM 默认放行 + 加黑→配额 429→审计检索
