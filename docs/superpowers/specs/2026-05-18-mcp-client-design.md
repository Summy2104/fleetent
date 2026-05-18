# MCP Client Design

## 和 tool_registry 的关系

MCP 工具在启动时注册进 tool_registry，和本地工具完全并列。agent_loop 和 LLM 看到的是统一的工具列表，不区分来源。

```
启动时：
  mcp_client 连接各 MCP server → 发现工具列表 → 注册进 tool_registry

运行时：
  agent_loop → tool_registry.dispatch(tool_name, args)
                    ↓ 透明路由
             本地工具直接执行 / MCP 工具通过 mcp_client 转发
```

这是 Claude Code 的实现方式：`claude mcp add` 后，MCP 工具与内置工具完全并列，LLM 无感知。

## 传输方式

优先实现 HTTP/SSE，stdio 后续补充。

| 传输 | 场景 | 状态 |
|------|------|------|
| HTTP/SSE | 远程 MCP server，公司内部部署服务 | 优先实现 |
| stdio | 本地子进程，如 filesystem server | 后续 |

## MCP Server 配置

```python
MCP_SERVERS: dict[str, MCPServerConfig] = {
    "internal-wiki": {
        "url": "http://internal.company.com/mcp",
        "auth": None,
    },
    "github": {
        "url": "https://api.github.com/mcp",
        "auth": {"type": "api_key", "env": "GITHUB_TOKEN"},
    },
    "google-calendar": {
        "url": "https://calendar.googleapis.com/mcp",
        "auth": {"type": "oauth2", "server_id": "google-calendar"},
    },
}
```

三种 auth 类型：
- `None` — 直连，无需授权
- `api_key` — Authorization header，从环境变量读取
- `oauth2` — 由 user_grant.py 管理 token，mcp_client 注入

## 工具注册（启动时）

```python
async def register_all(servers: dict, user_id: str) -> None:
    for server_id, config in servers.items():
        tools = await discover_tools(config)
        for tool in tools:
            def make_caller(sid, tname):
                def caller(**kwargs: Any) -> str:
                    return call_tool(sid, tname, kwargs, user_id)
                caller.__name__ = tname
                caller.__doc__ = tool.description
                return caller
            tool_registry._registry[tool.name] = (make_caller(server_id, tool.name), tool.schema)
```

工具名冲突处理：MCP 工具加 server 前缀，如 `github__create_issue`，避免和本地工具同名。

## 模块接口

```python
async def register_all(servers: dict[str, MCPServerConfig], user_id: str) -> None:
    """Discover tools from all configured MCP servers and register them."""

async def call_tool(server_id: str, tool_name: str, args: dict, user_id: str) -> str:
    """Call a tool on the specified MCP server. Handles auth injection."""
```

## 和权限设计的关系

- `agent_policy.py` 控制这个 agent 允许连哪些 MCP server（Layer 1）
- `user_grant.py` 提供 oauth2 类型 server 的 access token（Layer 2）
- `mcp_client.py` 只负责传输，不做权限判断
