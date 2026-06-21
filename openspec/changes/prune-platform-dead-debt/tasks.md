> 每个切片自上而下（UI → API → 表）独立删除；每个实现任务严格 TDD：先写/改测试见红 → 删除见绿。最窄命令 `uv run pytest <file>::<test> -x -q`。

## 1. Slice: 删 observability 孤儿 API

- [ ] 1.1 写测试：断言已挂载的 app 路由表中不含 `/admin/observability/traces|usage|performance`（或 `observability_admin_api` 不再被 `server.py` import）。当前应见红（路由仍注册）。
- [ ] 1.2 删除 `src/fleetent/platform/observability_management/` 整模块，移除 `server.py` 对 `observability_admin_api` 的 import 与 `include_router`；删除/调整断言该端点存在的既有测试。运行 1.1 见绿。

## 2. Slice: 删 Provider 路由墓碑

- [ ] 2.1 写测试：断言 provider 路由器注册路径不含 `/routes`、`/routes/{task_type}`、`/routes/{task_type}/preview`；并断言 `static/admin.html` 不含 `/providers/routes` 引用。当前应见红。
- [ ] 2.2 删除 `provider_admin_api.py` 中三个 404 路由桩与 `_routes_removed` 辅助函数；删除 admin UI 的 Providers→Routes 区块。运行 2.1 见绿。

## 3. Slice: 删 Chat playground 死 UI

- [ ] 3.1 写测试：断言 `static/admin.html` 不含 `/chat/start`、`/chat/sessions`、`/chat/{`（playground 调用）等引用。当前应见红。
- [ ] 3.2 移除 admin UI 的 Chat 标签页与 Sessions 页 playground 子面板及其 JS；保留 Sessions 治理（接管/释放/注入/强制结束/清空/重置）相关 UI 与调用。运行 3.1 见绿。

## 4. Slice: 删 Stats reports 死调用

- [ ] 4.1 写测试：断言 `static/admin.html` 不含 `/stats/reports` 引用（保留 `/stats/export`）。当前应见红。
- [ ] 4.2 移除 admin UI 的报表按钮与对 `POST /admin/stats/reports` 的调用；保留导出按钮。运行 4.1 见绿。

## 5. Slice: 删 skill 提案的平台审批桩

- [ ] 5.1 写测试：断言 skill 路由器注册路径不含 `/proposals/{proposal_id}/approve`、`/reject`，但仍含 `GET /proposals`、`GET /proposals/{proposal_id}/diff`；并断言 `static/admin.html` 不含提案 approve/reject 调用。当前应见红。
- [ ] 5.2 删除 `skill_admin_api.py` 中 `POST /proposals/{id}/approve`、`/reject` 两个 409 桩；移除 admin UI 提案视图的 approve/reject 按钮，保留列表与 diff 查看。运行 5.1 见绿。

## 6. Slice: drop `im_users.allowed` 死列

- [ ] 6.1 写测试（migration）：在 integration 层迁移到 head 后，断言 `im_users` 表无 `allowed` 列。当前应见红。
- [ ] 6.2 写测试（身份解析回归）：断言 IM 身份解析在无 `allowed` 列时，`users.status == "blocked"` 被拒、`active` 放行；且新建 `im_users` 映射的 insert 路径不写 `allowed`。当前应见红（代码仍引用/写 `allowed`）。
- [ ] 6.3 取当前最新 migration 版本之后的下一号，新增 forward 迁移 drop `im_users.allowed`；清理 `im_gateway_management/identity.py` 中对该列的兼容 shim 引用与 insert 写入。运行 6.1、6.2 见绿。

## 7. Change 收尾验证

- [ ] 7.1 `make test-pr` 全绿（unit + 层边界 + 改动文件 ruff）。
- [ ] 7.2 `uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线，无新增失败。
- [ ] 7.3 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过；确认改动未引入 agent→platform 反向依赖。
- [ ] 7.4 冒烟验证基线不受影响：在「无 platform、platform DB 表不存在」环境下 `fleetent agent run` 仍能完成一轮对话。
