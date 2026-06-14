# Tasks — external-services-admin-crud（P1）

> 依赖 P0 已 archive。TDD：测试任务前置。触及 DB/FastAPI 的测试放 integration。

## 1. external_services admin CRUD

- [ ] 1.1 写测试（integration）：admin POST/PUT/DELETE/GET `/admin/connectors` 走通，目录返回含 `protocol` 字段；`client_secret` 遮蔽；viewer 写被 403。
- [ ] 1.2 写测试（integration）：add `protocol="api_key"` 与 `protocol="oauth2_authcode"` 两种服务均正确落库并回显 protocol。
- [ ] 1.3 实现：admin 端点接 `external_services` store，承载 `protocol`/`kind`/endpoints/scopes/enabled；删除目录的 owning-agent 列与按 agent 过滤；写操作落审计。运行 1.1–1.2 见绿。

## 2. agent_service_grants 授权 admin

- [ ] 2.1 写测试（integration）：admin bind/unbind agent↔service 并设 `run_as`；列出 agent 已授权服务 / 服务已授权 agent；viewer 写被 403；写落审计。
- [ ] 2.2 实现：`/admin/agents/{name}/bindings/oauth` 接 `agent_service_grants` store（含 run_as），幂等。运行 2.1 见绿。

## 3. 收尾

- [ ] 3.1 `make test-pr` 全绿；`uv run pytest tests/integration -q` 无新增失败。
