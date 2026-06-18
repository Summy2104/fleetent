## 1. 租户管理 API 接线（tenancy router 注册）

- [x] 1.1 [测试] `tests/integration/test_tenancy_admin_api.py` 新增 `test_tenancy_router_is_registered`：调用 `GET /admin/tenancy/tenants` 验证返回 200 而非 404 → 运行必须红
- [x] 1.2 [实现] `server.py` 新增 `from fleetent.platform.tenancy import admin_api as tenancy_admin_api` 并 `app.include_router(tenancy_admin_api.router)`
- [x] 1.3 [验证] 运行 `uv run pytest tests/integration/test_tenancy_admin_api.py -x -q` → 确认绿

## 2. 租户管理 API 完整测试覆盖

- [x] 2.1 [测试] `tests/integration/test_tenancy_admin_api.py` 补充以下场景测试并运行见绿：
  - `test_create_tenant_success`
  - `test_list_tenants`
  - `test_create_team`
  - `test_set_user_tenant`
  - `test_set_approver`
  - `test_unauthenticated_returns_401`
  - `test_viewer_role_returns_403`

## 3. 节点管理 admin HTTP API

- [x] 3.1 [测试] `tests/integration/test_node_admin_api.py` 新增守门测试：`test_node_admin_routes_exist`（调用 `GET /admin/nodes` 验证 200 而非 404）→ 运行必须红
- [x] 3.2 [实现] 新建 `src/fleetent/platform/node_management/node_admin_api.py`，router prefix `/admin/nodes`，session token 鉴权（复用 `_require_admin` 模式）：
  - `POST /admin/nodes` — 注册节点，返回一次性 `service_key_plaintext_once`
  - `GET /admin/nodes` — 列举节点
  - `DELETE /admin/nodes/{node_id}` — 注销（有 pin 时 409）
  - `POST /admin/nodes/{node_id}/pin` — pin agent
  - `DELETE /admin/nodes/{node_id}/pin` — unpin agent
- [x] 3.3 [实现] `server.py` 注册 `node_admin_api.router`
- [x] 3.4 [测试] `tests/integration/test_node_admin_api.py` 补充完整场景测试并运行见绿：
  - `test_register_node_returns_service_key_once`
  - `test_duplicate_node_id_returns_409`
  - `test_list_nodes`
  - `test_deregister_node_success`
  - `test_deregister_pinned_node_returns_409`
  - `test_pin_and_unpin_agent`
  - `test_non_admin_returns_403`
- [x] 3.5 [验证] 运行 `uv run pytest tests/integration/test_node_admin_api.py -x -q` → 全绿

## 4. 共享记忆管理 HTTP API

- [x] 4.1 [测试] `tests/integration/test_shared_memory_admin_api.py` 新增守门测试：`test_shared_memory_routes_exist`（调用 `GET /admin/memory/shared` 验证 200 而非 404）→ 运行必须红
- [x] 4.2 [实现] 新建 `src/fleetent/platform/shared_memory_management/` 包，内含 `shared_memory_admin_api.py`，router prefix `/admin/memory/shared`，session token 鉴权：
  - `GET /admin/memory/shared` — 列举（`scope_type`/`scope_id` query 参数，`include_archived` 可选）
  - `POST /admin/memory/shared` — 创建
  - `PATCH /admin/memory/shared/{item_id}` — 更新
  - `POST /admin/memory/shared/{item_id}/archive` — 归档
- [x] 4.3 [实现] `server.py` 注册 `shared_memory_admin_api.router`
- [x] 4.4 [测试] 补充完整场景测试并运行见绿：
  - `test_list_shared_memory`
  - `test_create_shared_memory`
  - `test_update_shared_memory`
  - `test_archive_shared_memory`
  - `test_archived_excluded_by_default`
  - `test_non_admin_returns_403`
- [x] 4.5 [验证] 运行 `uv run pytest tests/integration/test_shared_memory_admin_api.py -x -q` → 全绿

## 5. KB 实体提取触发端点

- [x] 5.1 [测试] `tests/integration/test_kb_admin_api.py` 新增 `test_extract_entities_endpoint_exists`：调用 `POST /admin/kb/test-kb/extract-entities` 验证非 404 → 运行必须红
- [x] 5.2 [实现] `src/fleetent/platform/knowledge_base_management/kb_admin_api.py` 追加 `POST /admin/kb/{kb_id}/extract-entities` 端点，调用现有实体提取函数，返回 202；KB 不存在时返回 404
- [x] 5.3 [测试] 补充完整测试并运行见绿：
  - `test_extract_entities_triggers_task`
  - `test_extract_entities_unknown_kb_returns_404`
  - `test_extract_entities_non_admin_returns_403`
- [x] 5.4 [验证] 运行 `uv run pytest tests/integration/test_kb_admin_api.py -x -q` → 全绿

## 6. 收尾验证

- [x] 6.1 [验证] 运行 `make test-pr` → 全绿（unit + layer boundaries + ruff）
- [x] 6.2 [验证] 运行 `uv run pytest tests/integration -q` → 对照 main 基线无新增失败
- [x] 6.3 [验证] 运行 `make test-unit-ci` → unit 覆盖率不低于 76%
