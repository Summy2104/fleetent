## Context

`integrations/mcp/client.py` 有两条工具调用路径：`_call_stdio_tool`（经 `mcp` SDK `ClientSession`，结果是带属性的类型对象 `TextContent`/`ImageContent`/`EmbeddedResource`）与 `_call_http_tool`（手写 JSON-RPC，结果是 dict）。两者目前都只取 `content[0]` 且只读 `.text`/`["text"]`：

- stdio：`str(result.content[0].text)` —— 首块是 `ImageContent` 时无 `.text` 属性，抛 `AttributeError`。
- http：`contents[0].get("text", str(result))` —— 多块只剩首块；非文本块退化成把整个 result repr 塞进去。

两条路径都忽略 `isError` 与 `structuredContent`。结果形态虽不同（对象 vs dict），但规范化语义应当一致。

## Goals / Non-Goals

**Goals:**
- 一个被两条路径共用的纯函数，把"内容块列表 + structuredContent + isError"规范化为返回字符串。
- 多块聚合、非文本块安全 marker、`isError` 教学式错误、`structuredContent` 兜底。
- 对返回单文本块的现有服务行为不变（向后兼容）。

**Non-Goals:**
- 二进制内容落盘（hermes/claude-code 的 image→disk）——本次只用 marker 表示，落盘记入未来增强。
- 不改连接、注册、认证、分页、超时等任何其他逻辑（属后续变更）。
- 不改 agent_loop/registry 的 dispatch 契约（工具返回值仍是 `str`）。

## Decisions

**D1：单一共用规范化函数。** 新增 `_normalize_tool_result(content_blocks, *, structured_content, is_error) -> str`，两条路径都调用它。理由：消除两处重复且都写错的 `content[0]` 逻辑，单点测试。

**D2：内容块双形态适配。** 内容块可能是 SDK 对象或 dict。用一个 `_block_to_text(block) -> str` 以 duck-typing 读取：优先 `getattr`（对象），回退 `dict.get`（dict），统一取 `type`/`text`/`mimeType`/`data` 等字段。理由：避免在调用点先做对象→dict 转换，两形态共用一套提取。

**D3：非文本块 marker 格式。** text 块→原文；embedded resource 带 text→内联其文本（resource.text 或 resource.blob 的文本）；image/audio/blob→`[<kind>: <mimeType>]`（如 `[image: image/png]`），不输出 base64。字节数若可廉价得到（base64 解码长度估算）则附上，否则省略。理由：给模型足够语义线索而不撑爆上下文。

**D4：`isError` 语义。** `is_error` 为真时，返回值以明确前缀标记（如 `MCP tool error: ` + 规范化文本），仍返回字符串、不抛异常。理由：与项目「工具失败回传给模型」一致；agent_loop 把它当普通 tool_result，模型可读错纠正。

**D5：`structuredContent` 优先级。** 有内容块→以内容块聚合文本为准；内容块为空→`json.dumps(structuredContent)`。理由：避免内容块与结构化输出重复，且不丢结构化数据（openclaw 同款「空则用 structuredContent」）。

**D6：调用点改造最小化。** `_call_stdio_tool`/`_call_http_tool` 仅把"取首块文本"替换为"收集 content 列表 + structuredContent + isError → 调 `_normalize_tool_result`"。降级/认证短路等既有逻辑保持不动。

## Risks / Trade-offs

- 多块服务行为变化（原只露首块，现全部）→ 这正是要修的缺陷；单块路径有测试钉住向后兼容。
- marker 格式是客户端内部约定、非 MCP 标准 → 可接受（仅供 LLM 阅读）；保持简洁信息量。
- http 结果 dict 的 embedded resource 结构有嵌套（`resource.text`/`resource.blob`）→ 适配函数需容错缺字段，缺失时退化为 kind+mimeType marker，绝不抛。
- 估算 base64 字节数可能不精确 → 标注为近似或省略，不作为断言重点。
