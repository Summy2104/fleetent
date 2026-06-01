## 0. 前置确认

- [ ] 0.1 确认 `config/mcp.yaml` 仍然作为 legacy 路径 fail fast，不恢复兼容读取
- [ ] 0.2 确认本 change 不做 hot reload、Admin UI、runtime API 或 SQLite-backed MCP registry
- [ ] 0.3 确认 `settings.yaml` 只保留 MCP 全局策略，不保存 MCP server definitions

## 1. Settings MCP namespace cleanup

- [ ] 1.1 Write failing tests: `Settings()` 不再接受/暴露 `mcp.servers`
- [ ] 1.2 Write failing tests: `config/settings.yaml.example` 不包含 MCP server definitions
- [ ] 1.3 Implement: 将 `McpSettings` 收敛为全局策略，例如 `enabled`
- [ ] 1.4 Verify green: 运行 `uv run pytest tests/unit/test_config.py -x -q`

## 2. Dedicated MCP server file

- [ ] 2.1 Write failing tests: startup 从 `config/mcp.servers.yaml` 加载 MCP servers 并注册
- [ ] 2.2 Write failing tests: 缺失 `config/mcp.servers.yaml` 时启动成功且不注册 MCP servers
- [ ] 2.3 Write failing tests: `mcp.enabled=false` 时不读取/注册 dedicated MCP server file
- [ ] 2.4 Implement: 增加 dedicated MCP server file loader，并接入 server lifespan
- [ ] 2.5 Verify green: 运行 `uv run pytest tests/integration/test_server_lifespan.py -x -q`

## 3. Legacy path and examples

- [ ] 3.1 Write failing tests: 存在旧 `config/mcp.yaml` 时仍然 fail fast
- [ ] 3.2 Implement: 新增 `config/mcp.servers.yaml.example`，删除 `settings.yaml.example` 中的 server 列表示例
- [ ] 3.3 Verify green: 运行 `uv run pytest tests/unit/test_config.py tests/integration/test_server_lifespan.py -x -q`

## 4. Docs and final verification

- [ ] 4.1 更新 `docs/capabilities/mcp.md`、`docs/capabilities/deployment.md`、`docs/architecture.md`
- [ ] 4.2 运行 `uv run ruff format src tests`
- [ ] 4.3 运行 `uv run ruff check src tests`
- [ ] 4.4 运行 `uv run mypy src`
- [ ] 4.5 运行 `uv run pytest -x -q`
- [ ] 4.6 运行 `openspec validate mcp-server-config-split`
