## 1. 写失败测试（红）

- [ ] 1.1 改 unit `tests/unit/platform/node_management/test_node_config_payload.py::test_desired_state_payload_renders_mcp_servers_map`：server `env={"DOCS_TOKEN": "env:DOCS_TOKEN"}` 改为断言 `payload["mcpServers"]["docs"]["env"] == {"DOCS_TOKEN": "env:DOCS_TOKEN"}`（引用保留，删去旧的 `"env" not in` 断言）；跑该用例先见红
- [ ] 1.2 改 unit 同文件 `test_serialize_desired_state_payload_still_strips_secret_values`：server `env` 含明文+引用 `{"DOCS_TOKEN": "sk-inline-docs-secret", "DOCS_SHARED_TOKEN": "env:DOCS_SHARED_TOKEN"}`，断言 `payload["mcpServers"]["docs"]["env"] == {"DOCS_SHARED_TOKEN": "env:DOCS_SHARED_TOKEN"}` 且 `"sk-inline-docs-secret" not in str(payload)`；跑该用例先见红
- [ ] 1.3 新增 unit 同文件 `test_desired_state_payload_env_ref_collected_by_node`：`payload = desired_state_payload_from_agent_file(agent_file)` → `referenced_env_names(AgentFile.model_validate(payload))` 含该 MCP env 引用名（如 `DOCS_TOKEN`）；跑先见红（修复前 payload 无 env → 收不到）
- [ ] 1.4 新增 integration `tests/integration/test_node_mcp_env_delivery.py`：构造带 `mcp_servers[*].env={"JIRA_API_TOKEN": "env:JIRA_API_TOKEN"}` 的 `AgentFile`（model 用无需 secret 的目标）→ `desired_state_payload_from_agent_file` 作 node desired config，`secrets={"JIRA_API_TOKEN": "<v>"}`，`FakeBackend`+`respx` 跑 `NodeReconciler.reconcile`，断言写出的 `.env` 含 `JIRA_API_TOKEN=<v>`；跑先见红（修复前 env 被剥 → node 收不到名 → 不写值）

## 2. 实现（绿）

- [ ] 2.1 在 `src/fleetent/platform/agent_lifecycle/materialize.py` 加模块级 helper `_mcp_env_refs_by_id(dumped)`（按 server id 归集 `env` 中 `str` 且 `startswith("env:")` 的值，明文/非字符串丢弃）与 `_restore_mcp_env_refs(payload, refs)`（回挂到 `payload["mcpServers"][id]["env"]`，仅当该 id 已在 map 中）
- [ ] 2.2 在 `desired_state_payload_from_agent_file` 中：`model_dump` 后、`_strip_secret_plumbing` 前调 `_mcp_env_refs_by_id`；`_mcp_payload_to_map` 后调 `_restore_mcp_env_refs`；`_strip_secret_plumbing` 保持不动。令 1.1–1.4 全绿
- [ ] 2.3 跑 `uv run pytest tests/unit/platform/node_management/test_node_config_payload.py tests/integration/test_node_mcp_env_delivery.py -q` 全绿

## 3. 边界与静态校验

- [ ] 3.1 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` + `uv run pytest tests/unit/test_module_dependency_guardrails.py -q`：确认无新增跨包 / agent→platform 反向依赖
- [ ] 3.2 改动文件 `uv run ruff format` + `uv run ruff check` + `uv run mypy src/fleetent/platform/agent_lifecycle/materialize.py`

## 4. change 收尾

- [ ] 4.1 `make test-pr` 全绿
- [ ] 4.2 `uv run pytest tests/integration -q` 对照 main 无新增失败
- [ ] 4.3 archive 时按 `specs/node-desired-state-api` 的 MODIFIED delta 同步主 spec
