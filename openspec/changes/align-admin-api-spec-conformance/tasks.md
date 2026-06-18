## 1. 共享记忆创建状态码 → 201

- [ ] 1.1 [测试] `tests/integration/test_shared_memory_admin_api.py` 改 `test_create_shared_memory` 断言为 201 → 运行必须红（现 200）
- [ ] 1.2 [实现] `shared_memory_admin_api.py` 的 `POST /admin/memory/shared` 加 `status_code=201`
- [ ] 1.3 [验证] `uv run pytest tests/integration/test_shared_memory_admin_api.py -x -q` → 绿

## 2. node 注销 / unpin 状态码 → 204

- [ ] 2.1 [测试] `tests/integration/test_node_admin_api.py` 改注销成功、unpin 成功的断言为 204 → 红
- [ ] 2.2 [实现] `node_admin_api.py` 的 `DELETE /admin/nodes/{id}`、`DELETE /admin/nodes/{id}/pin` 加 `status_code=204`，返回空体
- [ ] 2.3 [验证] `uv run pytest tests/integration/test_node_admin_api.py -x -q` → 绿

## 3. 注销冲突 409 列出被 pin agent

- [ ] 3.1 [测试] `tests/integration/test_node_admin_api.py` 改 `test_deregister_pinned_node_returns_409` 断言 409 体含被 pin agent 列表（如 `pinned_agents`）→ 红
- [ ] 3.2 [实现] `node_admin_api.py` 注销路径捕获冲突后调 `placement_store.list_by_node(node_id)`，把被 pin agent id 放入 409 detail
- [ ] 3.3 [验证] `uv run pytest tests/integration/test_node_admin_api.py -x -q` → 绿

## 4. 收尾验证

- [ ] 4.1 [验证] `make test-pr` → 全绿
- [ ] 4.2 [验证] `uv run pytest tests/integration -q` → 对照 main 基线无新增失败
- [ ] 4.3 [验证] `make test-unit-ci` → unit 覆盖率 ≥ 76%
