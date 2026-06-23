> TDD 硬门禁：每个实现 task 先写测试见红 → 实现见绿。最窄命令：后端 `uv run pytest <file>::<test> -x -q`，前端 `yarn --cwd frontend vitest run <file>`。**测试任务在对应实现任务之前**。合并由主会话串行做。

## 1. Store 层（identity.py，TDD）

- [x] 1.1 写 integration 测试 `tests/integration/test_im_identity_admin_api.py` 的 store 部分：`list_mappings()` 返回带 `user_name`/`user_email` 的映射；`create_mapping()` 成功 / 目标用户不存在 ValueError / 重复 `(platform,platform_user_id)` ValueError / 写审计。先见红。
- [x] 1.2 在 `identity.py` 实现 `list_mappings` + `create_mapping`（named parameters、复用 `_conn`/`get_by_id`/`audit_log`），`__init__.py` re-export。跑 1.1 见绿。

## 2. 后端 admin API（im_identity_admin_api.py，TDD）

- [x] 2.1 写 integration 测试（FastAPI TestClient + session header）：`GET` 列表带用户名/邮箱、admin 可读 viewer 可读；`POST` 新增成功 201 / 目标用户不存在 404 / 重复 409 / viewer 403；`DELETE` 删除 204 / 不存在 404 / viewer 403；缺 token 401。先见红。
- [x] 2.2 实现 `im_identity_admin_api.py`（router 前缀 `/admin/im-identities`，自带 session-auth helper），在 `server.py` 注册（import + include_router）。跑 2.1 见绿。

## 3. 前端数据层（api.ts，TDD）

- [x] 3.1 写 `features/im-identities/api.test.tsx`（Vitest+MSW）：`useImMappingsQuery` 加载、`useCreateMappingMutation` 后刷新列表、`useDeleteMappingMutation` 后刷新列表；鉴权头 `Session`。先见红。
- [x] 3.2 实现 `features/im-identities/api.ts`（TanStack Query；映射列表 + 用户下拉 + 增删）。跑 3.1 见绿。

## 4. 前端页面（page.tsx，TDD）

- [x] 4.1 写 `features/im-identities/page.test.tsx`（MSW）：列表渲染平台/外部 ID/内部用户名+邮箱；表单新增后出现新行；删除后行消失。先见红。
- [x] 4.2 实现 `features/im-identities/page.tsx`（标题"用户-IM 关系"，新增表单 + 列表 + 删除）。跑 4.1 见绿。

## 5. 路由注册（共享缝）

- [x] 5.1 在 `app/routes.tsx` 加 import + 侧边栏 NavLink（"用户-IM 关系"→`/im-identities`）+ `<Route>`；在 `routes.test.tsx` 加断言（`/im-identities` 原生页 + nav 链接）。先见红再实现。

## 6. Change 收尾验证

- [x] 6.1 `uv run pytest tests/integration/test_im_identity_admin_api.py -q` 全绿。
- [x] 6.2 `make test-frontend` 全绿（vitest + 覆盖率 + tsc --noEmit + eslint）。
- [x] 6.3 `make test-pr` + `uv run pytest tests/integration -q` 对照 main 基线无新增失败。
- [ ] 6.4 人工核对：`/admin/ui` 内"用户-IM 关系"页可看映射、可增删。
