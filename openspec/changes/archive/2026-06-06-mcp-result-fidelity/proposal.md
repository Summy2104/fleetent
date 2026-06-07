## Why

MCP 工具调用的结果在返回给 agent_loop/LLM 之前，只读取了 `content[0].text` 一个内容块。这带来四个真实缺陷：多内容块结果被截断、stdio 路径在首块为图片等非文本块时崩溃（`ImageContent` 无 `.text`）、`isError` 被忽略导致工具自报错误被当成成功、`structuredContent` 被静默丢弃。这是接入真实 MCP 服务（返回图片、多块、结构化输出或显式错误）时的高频踩坑点，且其中包含会直接抛异常的 bug。

## What Changes

- 新增一个被 stdio 与 http 两条调用路径**共用**的结果规范化逻辑，统一处理 `CallToolResult` → 返回字符串：
  - **多内容块聚合**：纳入全部文本块（换行连接），不再只取首块。
  - **非文本块安全表示**：text→原文；embedded resource 带文本→内联其文本；image/audio/binary blob→简洁文本标记（如 `[image: <mimeType>, <n> bytes]`），不把 base64 灌入上下文，也不再崩溃。同时覆盖 stdio（MCP SDK 类型对象）与 http（dict）两种结果形态。
  - **`isError` 处理**：结果 `isError == true` 时返回明确标记的、含错误内容文本的教学式错误字符串（便于模型自纠），不抛异常——遵循「工具失败也回传给模型」的既有哲学。
  - **`structuredContent` 纳入**：有内容块时以内容块为主；内容块为空但有 `structuredContent` 时，将其序列化为 JSON 文本返回，避免静默丢弃。
- 修正过时的 `docs/capabilities/mcp.md`「现状」节，并新增本次 6 变更程序的差距分析与决策记录文档。

非破坏性：对返回单个文本块的现有服务，行为与现状一致（向后兼容）。

## Capabilities

### New Capabilities
- `mcp-result-handling`: 定义 MCP 工具调用结果（多内容块、非文本内容、`isError`、`structuredContent`）如何被规范化为返回给 agent 的文本，覆盖 stdio 与 http 两种传输。

### Modified Capabilities
<!-- 无：现有 mcp-client / mcp-http-streamable spec 未对结果内容处理作出任何要求，故为纯新增能力，不修改既有 spec 的 requirement。 -->

## Impact

- 代码：`src/fleetent/integrations/mcp/client.py`（`_call_stdio_tool`、`_call_http_tool` 改为调用共用的结果规范化函数；新增该函数）。
- 行为：MCP 工具结果对 agent 更完整、更稳健；返回图片的 stdio 工具不再崩溃；工具自报错误对模型可见。
- 测试：新增 `tests/unit/` 下结果规范化与两条调用路径（mock）的用例。
- 文档：`docs/capabilities/mcp.md` 现状修正；新增 `docs/records/mcp-enhancement-2026-06/{gap-analysis,decision-log}.md`。
- 依赖/外部系统：无新增依赖，不触碰 `data/`，不发真实网络请求或起真实子进程。
