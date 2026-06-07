## 1. McpServerConfig 超时字段 + client 用点（TDD）

- [x] 1.1 Write failing unit tests：`McpServerConfig` 含 `connect_timeout`（默认 10.0）/`call_timeout`（默认 30.0）；`_register_http_server` 与 `_probe_http_tools` 创建 `httpx.AsyncClient` 时用 `server.connect_timeout`、`_call_http_tool` 用 `server.call_timeout`（monkeypatch `httpx.AsyncClient` 捕获 `timeout` kwarg 后短路）。运行 `uv run pytest -x -q` 看红。
- [x] 1.2 Implement：`McpServerConfig` 加两字段；把 `_probe_once`/`_fetch_client_credentials_token`/`_register_http_server`/`_probe_http_tools` 的 `timeout=10.0` 改 `server.connect_timeout`、`_call_http_tool` 的 `timeout=30.0` 改 `server.call_timeout`；`_close_http_sessions` 保持固定。使 1.1 全绿。

## 2. agent.yaml 配置直达（TDD）

- [x] 2.1 Write failing unit tests：`McpServerSettings` 解析 `connect_timeout`/`call_timeout`（默认 10/30；声明时取声明值）。运行 `uv run pytest -x -q` 看红（字段尚未加）。
- [x] 2.2 Implement：`config.McpServerSettings` 加 `connect_timeout`/`call_timeout` 字段；`runtime/agent_app.py` 的 `McpServerConfig(...)` 映射透传两字段。使 2.1 全绿。

## 3. 文档与收尾

- [x] 3.1 更新 `docs/capabilities/mcp.md`（per-server 超时并入现状、移出规划中；progress-reset 标注延后理由）；`decision-log.md` 追加 Change 4 节。
- [x] 3.2 收尾全量校验：`env -u FLEETENT_HOME make test-unit-ci`、对改动文件 ruff/mypy、`uv run python scripts/check_test_layers.py` 全部通过。
