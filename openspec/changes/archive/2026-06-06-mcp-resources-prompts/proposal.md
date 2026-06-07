## Why

fleetent 只把 MCP 的 **tools** 暴露给 agent。MCP 还有 **resources**（服务端可提供的数据/文件）与 **prompts**（服务端定义的提示模板），服务在 `initialize` 的 capabilities 中声明（现已在 `server.capabilities` 捕获）。把它们以 capability-gated 的**合成工具**形式暴露，agent 即可经既有工具机制使用 resources/prompts，无需改 agent_loop。

## What Changes

- 对在 capabilities 中声明 `resources` 的服务，注册合成工具 `{server}__list_resources` 与 `{server}__read_resource(uri)`；声明 `prompts` 的服务，注册 `{server}__list_prompts` 与 `{server}__get_prompt(name, arguments?)`。
- 合成工具的调用分派到对应 MCP 方法：HTTP 经既有 JSON-RPC（`resources/list` 等），stdio 经 SDK（`list_resources()` 等）；结果序列化为 JSON 文本返回。
- **capability 门控**：仅当服务 advertised capabilities 含对应键时才注册——不给不支持的服务注册无效工具。
- 与既有机制一致：合成工具走 `{server}__*` 命名空间，故自动受降级 schema 可见性过滤；stdio `tools/list_changed` 刷新后会一并重注册（不丢失）。

非破坏性：不声明 resources/prompts 的服务不受影响。

## Capabilities

### New Capabilities
- `mcp-resources-prompts`: 定义按服务 advertised capabilities 把 MCP resources/prompts 暴露为合成工具的行为（门控、分派、结果、与刷新/降级的交互）。

### Modified Capabilities
<!-- 无：现有 spec 未涉及 resources/prompts，为纯新增能力。 -->

## Impact

- 代码：`src/fleetent/integrations/mcp/client.py`——新增 `_UTILITY_TOOL_SPECS`、`_register_utility_tools`/`_register_utility_tool`、`_call_utility`（+ http/stdio 分派）、`_utility_params`、`_jsonify`；在 `_register_http_server`/`_register_stdio_server`/`_reregister_stdio_tools` 末尾调用 `_register_utility_tools`。
- 行为：声明 resources/prompts 的 MCP 服务，其 resources/prompts 经合成工具对 agent 可用；其他服务不变。
- 测试：`tests/unit/` 新增门控、参数构建、JSON 化、http/stdio 分派、刷新后保留等用例（mock，无真实 I/O）。
- 不在范围（记为未来）：resources/prompts 的 `list_changed` 动态刷新（本程序 Change 5 只做 tools）；resources 作为 @-mention、prompts 作为 slash-command 的「一等公民」UX（合成工具已足以让 agent 访问）。
- 依赖/外部系统：无新增依赖，不触碰 `data/`。
