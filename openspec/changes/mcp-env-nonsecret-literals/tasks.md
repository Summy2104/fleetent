## 1. 写失败测试（红）

- [x] 1.1 新增 unit `tests/unit/platform/node_management/test_node_config_payload.py::test_desired_state_payload_keeps_plaintext_mcp_env`：构造 MCP server `env={"ATLASSIAN_API_TOKEN": "env:ATLASSIAN_API_TOKEN", "ATLASSIAN_USER_EMAIL": "r.intern.dev@example.test", "ATLASSIAN_SITE_NAME": "antalpha"}` → `payload = desired_state_payload_from_agent_file(...)`，断言 `payload["mcpServers"][id]["env"]` 同时含 `env:` 引用与两个明文键值；跑该用例先见红（修复前明文被剥）
- [x] 1.2 **重写**既有安全测试 `test_serialize_desired_state_payload_still_strips_secret_values` 为新契约（重命名为 `test_serialize_desired_state_payload_keeps_env_strips_credential_ref`）：server `env={"DOCS_TOKEN": "plaintext-docs-config", "DOCS_SHARED_TOKEN": "env:DOCS_SHARED_TOKEN"}` + 顶层/server `credential_ref="env:DOCS_SHARED_SECRET"`，断言 `payload["mcpServers"][id]["env"]` 同时含明文 `DOCS_TOKEN` 与引用 `DOCS_SHARED_TOKEN`，且 `"credential_ref" not in payload["mcpServers"][id]`；跑先见红（修复前明文 DOCS_TOKEN 被剥）。在测试 docstring 注明新契约：env 明文=非密配置照常下发，真 secret 走 `env:` + 存储
- [x] 1.3 复核既有 `test_desired_state_payload_renders_mcp_servers_map`（env 仅 `env:` 引用）与 `test_desired_state_payload_env_ref_collected_by_node` 仍**绿**（`env:` 引用与 referenced_env_names 收集行为不变）
- [x] 1.4 新增 integration `tests/integration/test_node_mcp_env_delivery.py` 用例 `test_plaintext_mcp_env_written_to_agent_yaml`：构造带 `mcp_servers[*].env={"ATLASSIAN_API_TOKEN":"env:ATLASSIAN_API_TOKEN","ATLASSIAN_SITE_NAME":"antalpha","ATLASSIAN_USER_EMAIL":"r.intern.dev@example.test"}` 的 `AgentFile` → desired config，`FakeBackend`+`respx` 跑 `NodeReconciler.reconcile`，断言写出的 `agent.yaml` 的 `mcpServers.<id>.env` 含 `ATLASSIAN_SITE_NAME: antalpha` 与该 email 明文；跑先见红

## 2. 实现（绿）

- [x] 2.1 在 `src/fleetent/platform/agent_lifecycle/materialize.py` 把 `_mcp_env_refs_by_id` 的保留判定由 `isinstance(v, str) and v.startswith("env:")` 改为 `isinstance(v, str)`（`env:` 引用与明文一并捕获回挂）；更新该函数 docstring 与 `desired_state_payload_from_agent_file` 内相关注释，写明新契约：`env:` = secret 指针、明文 = operator 声明的非密配置、`credential_ref` 仍剥。令 1.1、1.2、1.4 转绿，1.3 保持绿
- [x] 2.2 跑 `uv run pytest tests/unit/platform/node_management/test_node_config_payload.py tests/integration/test_node_mcp_env_delivery.py -q` 全绿（8 passed）

## 3. 边界与静态校验

- [x] 3.1 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` + `uv run pytest tests/unit/test_module_dependency_guardrails.py -q`：确认无新增跨包 / agent→platform 反向依赖（边界脚本通过；guardrails 13 passed）
- [x] 3.2 改动文件 `uv run ruff format` + `uv run ruff check`（All checks passed）+ `uv run mypy src/fleetent/platform/agent_lifecycle/materialize.py`（仅 `:379` OAuth 赋值一处既有 error，与本改动无关、main 上已存在；本改动未引入新 mypy 错误）

## 4. change 收尾

- [x] 4.1 `make test-pr`：4019 passed，2 failed（`test_config.py::test_observability_logging_defaults`、`test_admin_entrypoint_cleanup.py::test_legacy_admin_cli_package_is_not_importable`）——二者均为既有失败，已在干净 origin/main（stash 本改动）复现，本改动新增失败数 = 0
- [x] 4.2 `make test-integration-ci`：2113 passed，1 failed（`test_pilot_readiness_admin.py::test_validate_config_cli_json_outputs_deterministic_summary`）——同为既有失败，已在干净 origin/main 复现，本改动新增失败数 = 0；本 change 新增的 `test_plaintext_mcp_env_written_to_agent_yaml` 在该轮通过
- [ ] 4.3 archive 时按 `specs/node-desired-state-api` 的 MODIFIED delta 同步主 spec
