## 1. users.email 规范化 + 租户内 partial unique（迁移 + 写入侧）

- [x] 1.1 **测试（红）**：`tests/integration/`（如 `test_user_email_join.py`）：跑 Alembic 到 head 后，(a) 同租户插两个规范化相同 email → 第二条被 partial `UNIQUE(tenant_id,email)` 拒；(b) 不同租户同 email → 允许；(c) email=NULL 多行 → 允许（不受唯一约束）；(d) `create_user(email="  Alice@Co ")` → 存为 `alice@co`。先跑见红。
- [x] 1.2 **实现（绿）**：新增 Alembic 迁移加 partial unique index（`WHERE email IS NOT NULL`）；`create_user`/`set_profile` 写入前 `lower(trim)` 规范化 email。跑见绿。

## 2. get_by_email 改 tenant 范围 + 规范化 + 调用点 survey

- [x] 2.1 **测试（红）**：`get_by_email(tenant_id, email)`：`"  Alice@Co "` 命中库里同租户 `alice@co`；跨租户同 email **不**命中（不同人）。先跑见红。
- [x] 2.2 **实现（绿）**：`get_by_email` 加 `tenant_id` 参数 + 规范化比较；**改全部调用点**（grounding 已 survey：`user_store.py:295`、`user_store.py:338`、`platform/user_management/user_admin_api.py:68` `_resolve_login_user`）补 tenant。注意 `_resolve_login_user`（登录）的 tenant 来源——按其上下文定（如内置 admin/web 用户的租户）。跑见绿 + 既有 login 测试不破。

## 3. resolve_or_provision（email 并号解析，平台侧）

- [x] 3.1 **测试（红）**：新增 `resolve_or_provision(tenant, *, verified_email=None, channel=None, platform_user_id=None)` 的 integration 测试：
  - verified_email 命中既有 user + channel 未映射 → **attach**（写 im_users → 既有 user_id），不建新 user；
  - verified_email 未命中 → 建 email-keyed user + attach channel；
  - 无 email → channel-keyed 建 user（现行）；
  - **attach-only / 不 merge（决策 1）**：channel 身份**已**有 im_users 映射时，即便 verified_email 匹配到**另一个** user，也用**现映射**、不改挂不合并；
  - **race**：并发首触发同 email → 第二个 insert 撞唯一约束 → 捕获后转 lookup-link（镜像现有 `INSERT OR IGNORE` 竞态）。先跑见红。
- [x] 3.2 **实现（绿）**：在 `platform/im_gateway_management/identity.py`（或同包新模块）实现 `resolve_or_provision`（碰 user_store + im_users；**不放 user_store**，守"user_store 不依赖 platform"）。跑见绿。

## 4. IM get_or_create 路由经 resolve_or_provision

- [x] 4.1 **测试（红）**：`get_or_create` 在**有 verified email**时经 `resolve_or_provision`（命中既有 email-keyed user 则 attach、不新建）；**无 email**时维持现行 channel-keyed。先跑见红。
- [x] 4.2 **实现（绿）**：`get_or_create` 改为委托 `resolve_or_provision`（email 由调用方传，当前 IM 无 email 则走 fallback；#4 补 email 后自然走并号）。跑见绿。

## 5. 迁移撞存量重复 → 报告中止

- [x] 5.1 **测试（红）**：seed 同租户规范化重复 email 的存量行，跑迁移 → **迁移中止 + 输出冲突报告**，**不自动合并**任何 user。先跑见红。
- [x] 5.2 **实现（绿）**：迁移先 backfill `lower(trim)`，再检测 `(tenant, norm_email)` 重复；有则 raise 带清单的错误中止。跑见绿。

## 6. 收尾

- [x] 6.1 `make test-pr` 全绿（对照 main 基线无新增失败）+ 跑相关集成 `uv run pytest tests/integration/test_user_email_join.py tests/integration/test_auth.py tests/integration/test_api_key_auth.py -q` + 既有 login/im 测试无新增失败。
- [x] 6.2 **跨切面提示**：本 change 含 **Alembic 迁移 + 改 user_store 公开 API（被广泛依赖）**——属跨切面，收尾跑**更广的集成**（不只 scoped），确认无连带回归（任何建 user / 登录 / IM 解析的测试）。覆盖率门禁 `make test-unit-ci`（--fail-under=76）不被拉破。
- [x] 6.3 merge 后跑迁移 head 自检 `uv run alembic heads` 确认**单一 head**（并行 change 可能占号，撞号则改本迁移 down_revision 重链）。
