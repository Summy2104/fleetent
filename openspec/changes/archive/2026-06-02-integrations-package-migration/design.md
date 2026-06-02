## Context

当前 integrations 相关 legacy 文件：

| Legacy file | 当前职责 | 目标模块 |
| --- | --- | --- |
| `mcp_client.py` | MCP server 注册、HTTP / stdio transport、tool call dispatch | `integrations.mcp.client` |
| `sandbox_client.py` | Docker sandbox workspace create / exec / destroy | `integrations.sandbox.client` |

主要调用方：

- `server.py` 使用 `McpServerConfig` 和 MCP lifecycle。
- `tools.py` 使用 `SandboxClient`。
- tests 仍大量使用旧路径 `fleetent.mcp_client` / `fleetent.sandbox_client`。

这说明迁移需要保留旧路径 shim，同时让新代码可以使用 canonical path。

## Target Structure

目标结构：

```text
src/fleetent/integrations/
  __init__.py
  mcp/
    __init__.py
    client.py
  sandbox/
    __init__.py
    client.py

src/fleetent/mcp_client.py
src/fleetent/sandbox_client.py
```

旧顶层文件只保留 re-export shim。示例：

```python
"""Compatibility shim for MCP integrations."""

from fleetent.integrations.mcp.client import McpServerConfig, call_tool, close, register_all

__all__ = ["McpServerConfig", "call_tool", "close", "register_all"]
```

实际 `__all__` 必须覆盖迁移前被测试或调用方依赖的 public API。对于 `_make_tool_name`、`_register_server`
等测试已经依赖的 helper，可以作为迁移期 compatibility export 保留；但新代码不应继续新增对这些 private helper 的依赖。

## Public API Strategy

新 canonical imports：

```python
from fleetent.integrations.mcp import McpServerConfig, register_all
from fleetent.integrations.sandbox import SandboxClient
```

旧 imports 继续可用：

```python
from fleetent.mcp_client import McpServerConfig
from fleetent.sandbox_client import SandboxClient
```

shim 不允许：

- 创建 MCP sessions。
- 创建 Docker subprocess。
- 承载 mutable registry。
- 包含 transport / sandbox 业务逻辑。

MCP client 原有 module-level state，包括 `_server_registry`、`_active_sessions`、`_exit_stack`，必须迁入
`integrations.mcp.client`。测试 monkeypatch 应优先迁到新 canonical path。

## Import Migration

建议更新：

- `server.py` 使用 `fleetent.integrations.mcp`。
- `tools.py` 使用 `fleetent.integrations.sandbox`。
- 新增 compatibility tests 同时覆盖旧路径。

不强制在本 change 中迁移所有测试到 canonical path；但新增测试和 monkeypatch 应使用新路径，避免 shim 承载状态。

## Risks

- MCP module-level registry 如果留在 shim，会导致旧路径和新路径状态分裂。
- `server.py` lifecycle monkeypatch 如果仍 patch 旧 shim，可能无法影响真实实现。
- `_make_tool_name` / `_register_server` 等 private helper 被测试使用，迁移时容易漏 export。
- sandbox client 的 Docker 参数不应在迁移中被顺手改动。

## Verification

必须验证：

- 新 canonical import 路径可用。
- 旧 import 路径仍可用。
- MCP client integration tests 通过。
- Sandbox client / tools tests 通过。
- server lifespan tests 通过。
- module boundary check 通过。
- 完整测试通过。

本 change 不改变 MCP 或 sandbox 行为，只改变代码组织和 import 边界。
