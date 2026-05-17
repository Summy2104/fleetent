# tool_registry.py + tools.py

## 注册机制：side-effect import

`@tool` 装饰器在模块加载时执行（不是调用时）。`import mini_agent.tools` 这一行就触发了所有 `@tool` 的注册，无需显式调用。

## arguments 为什么是 JSON 字符串

LLM 的输出本质是文本。它生成 `{"city": "Beijing"}` 这个字符串，API 原样放进 `arguments` 字段。所以 `dispatch` 必须先 `json.loads(arguments_json)` 再 `**kwargs` 解包调用。

## dispatch 做什么

接收 tool 名称和 JSON 格式参数字符串 → 查 `_registry` → 解包参数 → 调用函数 → 返回字符串结果。

## 没有类型注解时

`_py_type_to_json` 收到 `inspect.Parameter.empty`，走到最后返回 `"string"`。LLM 会把该参数当字符串处理。

## inspect.Parameter.empty 的两个用途

- `param.annotation is inspect.Parameter.empty` → 没有类型注解
- `param.default is inspect.Parameter.empty` → 没有默认值（→ 加入 required）
