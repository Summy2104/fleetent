# tool_registry.py + tools.py

## 注册机制：side-effect import

`@tool` 装饰器在模块加载时执行（不是调用时）。`import fleetent.tools` 这一行就触发了所有 `@tool` 的注册，无需显式调用。`agent_loop.py` 顶部有一行 `import fleetent.tools  # noqa: F401`，这是故意的。

## arguments 为什么是 JSON 字符串

LLM 的输出本质是文本，它生成 `{"city": "Beijing"}` 这个字符串，API 原样放进 `arguments` 字段。`dispatch` 必须先 `json.loads(arguments_json)` 再 `**kwargs` 解包调用。

## dispatch 做什么

接收 tool 名称和 JSON 格式参数字符串 → 查 `_registry` → 解包参数 → 调用函数 → 返回字符串结果。

## 没有类型注解时

`_py_type_to_json` 收到 `inspect.Parameter.empty`，走到最后返回 `"string"`。LLM 会把该参数当字符串处理。

## inspect.Parameter.empty 的两个用途

- `param.annotation is inspect.Parameter.empty` → 没有类型注解
- `param.default is inspect.Parameter.empty` → 没有默认值（→ 加入 `required`）

## MCP 工具的命名约定

通过 `mcp_client.py` 注册的外部工具使用双下划线命名：`{server_id}__{tool_name}`，例如 `linear__create_issue`。单下划线是工具名本身的一部分，双下划线是命名空间分隔符。这样 `dispatch` 查 `_registry` 时不需要特殊处理——MCP 工具和内置工具共用同一个 registry。

## access control

`agent_policy.py` 在 dispatch 之前用 fnmatch 做工具白名单检查（`allowed_tools` 字段），阻断未授权的工具调用。默认 `allowed_tools=["*"]` 即全部允许。
