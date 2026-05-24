# mcp_client.py

## 职责

启动时从 MCP HTTP 服务器发现工具列表，注册为本地工具；运行时把工具调用转发给对应服务器。

## 注册流程

```
config/mcp.yaml → register_all(servers)
    └─ _register_server(server)
           ├─ POST {url}/ {method: "tools/list"}   ← 发现工具
           └─ for each tool: _register_tool(server, tool_name, tool_def)
                  └─ tr._registry[tool_name] = (call_fn, schema)
```

`call_fn` 是一个闭包，捕获 `server` 和 `tool_def["name"]`，调用时转发到 `call_tool()`。

## 命名约定：双下划线

```python
def _make_tool_name(server_id: str, tool_name: str) -> str:
    return f"{server_id}__{tool_name}"
```

`linear__create_issue`、`github__list_prs`。双下划线是命名空间分隔符——单下划线可能是工具名的一部分，双下划线约定俗成地表示"属于某个命名空间"。

与内置工具共用同一 `_registry`，dispatch 不需要特殊处理。

## 运行时调用流程

```
dispatch("linear__create_issue", args)
    └─ call_fn(**args)
           └─ call_tool("linear", "create_issue", args)
                  └─ POST {url}/ {method: "tools/call", params: {name, arguments}}
```

`_server_registry` 按 `server_id` 保存 `McpServerConfig`，`call_tool` 用它找到 URL 和认证信息。

## 认证

`auth_type="api_key"` 时读取 `api_key_env` 指定的环境变量，设为 `Authorization: Bearer {key}` header。`auth_type="none"` 时不设 header。目前不支持 OAuth2（声明了但未实现）。

## 不可达服务器不阻塞启动

```python
try:
    await _register_server(server)
except Exception as exc:
    logger.warning("mcp_server_unavailable ...")
```

注册失败的服务器被跳过，其他服务器和内置工具不受影响。工具在运行时不可用时 dispatch 会抛 KeyError。
