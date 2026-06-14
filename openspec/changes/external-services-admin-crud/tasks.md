# Tasks — external-services-admin-crud（P1）

> 依赖 P0 已 archive。TDD：测试任务前置。触及 DB/FastAPI 的测试放 integration。

## 1. external_services admin CRUD

- [ ] 1.1 写测试（integration）：admin POST/PUT/DELETE/GET `/admin/connectors` 走通，目录返回含 `protocol` 字段；`client_secret` 遮蔽；viewer 写被 403；`agent_id` 查询参数不再改变结果集。
- [ ] 1.2 写测试（integration）：add `protocol="oauth2"` 与 `protocol="apikey"` 两种服务均正确落库并回显 protocol；底层断言走 `external_services` 而非 legacy overlay 语义。
- [ ] 1.3 实现：`connector_admin_api` 改接 `external_service_store`，扩 `protocol` 从 OAuth-only 到 `oauth2|apikey`，维持现有 `/admin/connectors` 路由兼容面；目录显式为单层全局，写操作落审计。运行 1.1–1.2 见绿。

## 2. agent_service_grants 授权 admin

- [ ] 2.1 写测试（integration）：admin bind/unbind agent↔service 并设 `run_as`；`GET /admin/agents/{name}/bindings/oauth` 返回 grant 列表而非旧 `connector_ids`；提供某服务已授权 agent 的读取面；viewer 写被 403；写落审计。
- [ ] 2.2 实现：`/admin/agents/{name}/bindings/oauth` 改接 `agent_service_grant_store`（含 run_as），保留现有路由路径兼容；绑定幂等，未知 service 仍 404。运行 2.1 见绿。

## 3. 收尾

- [ ] 3.1 `make test-pr` 全绿；`uv run pytest tests/integration -q` 无新增失败。
