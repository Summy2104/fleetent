## Why

`mcp_client.py` 和 `sandbox_client.py` 都属于外部能力接入：

- MCP client 负责连接外部 MCP servers，并把外部工具注册到本地 tool registry。
- Sandbox client 负责通过 Docker 提供隔离执行环境。

这两类能力不是 runtime 核心逻辑，也不属于 platform / intelligence / channels。继续平铺在 `src/fleetent`
根目录，会让后续 runtime、tools 和 server 代码直接依赖 legacy 路径，不利于形成模块化单体边界。

本 change 只做结构迁移：把 MCP 和 sandbox 实现迁入 `fleetent.integrations` package，并保留旧 import
路径 thin shim。

## What Changes

- 新增 `src/fleetent/integrations/` package。
- 新增 `src/fleetent/integrations/mcp/` package，并迁入 MCP client 实现。
- 新增 `src/fleetent/integrations/sandbox/` package，并迁入 sandbox client 实现。
- 将旧顶层文件改为 compatibility shim：
  - `src/fleetent/mcp_client.py`
  - `src/fleetent/sandbox_client.py`
- 保持 `McpServerConfig`、`register_all()`、`call_tool()`、`SandboxClient`、`ExecResult` 等 public API 不变。
- 更新必要内部 import 到 canonical path。
- 增加或调整测试，证明新 package import 和旧 import 路径都可用。
- 更新 source module organization roadmap，记录 integrations package migration spec。

## Out of Scope

- 不修改 MCP transport 行为。
- 不修改 MCP tool naming 格式。
- 不修改 MCP server 配置格式。
- 不修改 sandbox Docker 参数或资源限制。
- 不修改 `tool_registry.py` 的注册机制。
- 不修改 `tools.py` 的工具行为。
- 不新增数据库 schema 或配置 namespace。
- 不删除旧 import shim。

## Module Boundary Impact

- **Owning package**：`integrations`。
- **Public API surface**：
  - 新增 canonical import 路径：
    - `fleetent.integrations.mcp`
    - `fleetent.integrations.mcp.client`
    - `fleetent.integrations.sandbox`
    - `fleetent.integrations.sandbox.client`
  - 旧路径 `fleetent.mcp_client`、`fleetent.sandbox_client` 保留为 shim。
- **Owned tables**：无。
- **Config namespace**：无新增配置；MCP / sandbox 继续使用现有配置来源。
- **Cross-module dependencies**：
  - server 可以通过 `fleetent.integrations.mcp` public API 注册 MCP servers。
  - tools 可以通过 `fleetent.integrations.sandbox` public API 创建 sandbox client。
  - integrations 可以注册工具到 `tool_registry`，但不得 import agent runtime entrypoint。
- **Migration / shim plan**：
  - 第一步迁移实现到 `fleetent.integrations.mcp.client` 和 `fleetent.integrations.sandbox.client`。
  - 第二步在 package `__init__.py` re-export public API。
  - 第三步将旧顶层文件改为只 re-export public names 的 thin shim。
  - 第四步更新项目内部明显属于 integrations 的 import 到 canonical path。
