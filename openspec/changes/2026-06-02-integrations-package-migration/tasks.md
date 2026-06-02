## 0. 前置确认

- [ ] 0.1 确认本 change 只迁移 integrations 文件结构，不改 MCP 或 sandbox 行为
- [ ] 0.2 确认不新增数据库 migration
- [ ] 0.3 确认不新增配置 namespace
- [ ] 0.4 确认旧顶层文件只保留 thin shim

## 1. Package skeleton and import compatibility

- [ ] 1.1 Write failing tests: `fleetent.integrations.mcp` 和 `fleetent.integrations.mcp.client` 可 import
- [ ] 1.2 Write failing tests: `fleetent.integrations.sandbox` 和 `fleetent.integrations.sandbox.client` 可 import
- [ ] 1.3 Write failing tests: 旧路径 `fleetent.mcp_client` 和 `fleetent.sandbox_client` 仍暴露迁移前 public API
- [ ] 1.4 Implement: 新增 integrations package skeleton
- [ ] 1.5 Verify green: 运行相关 import compatibility tests

## 2. Move MCP integration

- [ ] 2.1 Write failing tests: MCP canonical path 暴露 `McpServerConfig`、`register_all()`、`close()`、`call_tool()`
- [ ] 2.2 Write failing tests: MCP legacy path 与 canonical path 共享同一 module-level registry 状态
- [ ] 2.3 Implement: 迁移 `mcp_client.py` 到 `integrations/mcp/client.py`
- [ ] 2.4 Implement: `integrations/mcp/__init__.py` re-export MCP public API
- [ ] 2.5 Implement: 顶层 `mcp_client.py` 改为 thin shim
- [ ] 2.6 Verify green: 运行 `uv run pytest tests/integration/test_mcp_client.py -x -q`

## 3. Move sandbox integration

- [ ] 3.1 Write failing tests: sandbox canonical path 暴露 `SandboxClient` 和 `ExecResult`
- [ ] 3.2 Write failing tests: sandbox legacy path 与 canonical path 暴露同一 class objects
- [ ] 3.3 Implement: 迁移 `sandbox_client.py` 到 `integrations/sandbox/client.py`
- [ ] 3.4 Implement: `integrations/sandbox/__init__.py` re-export sandbox public API
- [ ] 3.5 Implement: 顶层 `sandbox_client.py` 改为 thin shim
- [ ] 3.6 Verify green: 运行 `uv run pytest tests/unit/test_sandbox_client.py tests/unit/test_tools.py -x -q`

## 4. Canonical imports and cleanup

- [ ] 4.1 Write failing tests: server lifespan tests patch canonical MCP module and still pass
- [ ] 4.2 Write failing tests: tools tests patch canonical sandbox module and still pass
- [ ] 4.3 Implement: 将 `server.py` 和 `tools.py` 的 integrations import 更新到 canonical path
- [ ] 4.4 Implement: 确保 shim 不保留 MCP registry、exit stack 或 sandbox 逻辑
- [ ] 4.5 Verify green: 运行 `uv run pytest tests/integration/test_server_lifespan.py tests/unit/test_tools.py -x -q`

## 5. Docs and final verification

- [ ] 5.1 更新 `docs/architecture/source-module-organization-roadmap.md`，标记 integrations package migration 已有 implementation spec
- [ ] 5.2 更新 OpenSpec `module-boundaries` 说明 integrations package 迁移
- [ ] 5.3 运行 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`
- [ ] 5.4 运行 `uv run ruff format src tests`
- [ ] 5.5 运行 `uv run ruff check src tests`
- [ ] 5.6 运行 `uv run mypy src`
- [ ] 5.7 运行 `uv run pytest -x -q`
- [ ] 5.8 运行 `openspec validate 2026-06-02-integrations-package-migration --strict`
- [ ] 5.9 运行 `git diff --check`
