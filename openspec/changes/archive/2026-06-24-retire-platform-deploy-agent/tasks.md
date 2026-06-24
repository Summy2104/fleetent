## 1. 删除 deploy_agent 端点

- [x] 1.1 写测试（integration）：platform app **无** `POST /admin/agents/{name}/deploy` 路由（请求返回 404），落实 spec scenario "No platform endpoint writes an agent home"；先见红
- [x] 1.2 删除 `agent_admin_api.deploy_agent` 函数 + `@router.post("/agents/{name}/deploy")` 路由 + 其 `agent.deploy` audit 写入；保留 `_build_agent_yaml` 与 `export_agent_yaml`；令 1.1 见绿
- [x] 1.3 删除/改写 deploy_agent 的既有测试调用：`tests/unit/test_coverage_admin_connector_handlers.py`（deploy_agent 直接调）、`tests/integration/test_agent_admin_api.py`（`/deploy` POST 用例）

## 2. 保留只读投影回归

- [x] 2.1 跑 `export_agent_yaml`（`GET /admin/agents/{name}/agent-yaml`）相关测试，确认回显路径不受影响、`_build_agent_yaml` 仍工作（落实 spec scenario "Read-only config projection is allowed"）

## 3. 收尾

- [x] 3.1 grep 确认无残留对 `deploy_agent` / `POST .../deploy` 的引用（src + tests + 前端 + 文档）
- [x] 3.2 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 无新增跨包 internal import 违规
- [x] 3.3 change 收尾：`make test-pr` + `make test-unit-ci`（覆盖率门禁）全绿，对照 main 无新增失败；相关 `test_agent_admin_api` integration 无新增失败
