## Context

Change 2 已在 `server.capabilities`（dict）捕获服务 advertised capabilities（http 从 init result，stdio 从 `session.initialize()`）。现有工具经 `{id}__tool` 注册进共享 `tr._registry`（仅 scope=None），降级时由 `_schema_visibility` 按前缀隐藏；Change 5 的 `_reregister_stdio_tools` 在刷新时按前缀删后重注册。SDK stdio 有 `list_resources()/read_resource(uri)/list_prompts()/get_prompt(name, arguments)`；HTTP 经 `_post_jsonrpc(method, params)` 通用。

## Goals / Non-Goals

**Goals:**
- 按 capabilities 门控注册 resources/prompts 合成工具（`{id}__list_resources` 等）。
- 调用分派到对应 MCP 方法（http JSON-RPC / stdio SDK），结果 JSON 文本化。
- 与降级（前缀可见性）、刷新（Change 5 重注册）一致。

**Non-Goals:**
- resources/prompts 的 `list_changed` 动态刷新（本程序只对 tools 做）。
- resources→@mention / prompts→slash 的一等公民 UX（合成工具已让 agent 可访问）。
- 不改 agent_loop——合成工具就是普通工具。

## Decisions

**D1 合成工具声明式 + 门控。** `_UTILITY_TOOL_SPECS = ((util_name, cap_key, method, description, schema), ...)` 四项。`_register_utility_tools(server, scope)`：仅 scope=None；`cap_key in (server.capabilities or {})` 才注册。理由：与现有「仅 scope=None 进共享表」一致，不给不支持的服务注册无效工具。

**D2 统一分派 `_call_utility`。** 闭包调用 `_call_utility(server_id, util_name, args, scope)`：先做与 `_call_*_tool` 同款的 auth/health 短路（unavailable 返回标准文本）；再按 transport 分派——http 用 `_post_jsonrpc(client, server, method, _utility_params(util_name, args))`（用 `server.call_timeout`、disconnect→`_handle_disconnect`），stdio 按 util_name 调对应 SDK 方法（同样 disconnect 处理）。结果经 `_jsonify` 序列化。

**D3 `_jsonify` 兼容 pydantic 与 dict。** stdio SDK 返回 pydantic（`model_dump(mode="json", exclude_none=True)`），http 返回 dict；统一 `json.dumps(..., ensure_ascii=False, default=str)`，异常回退 `str()`。

**D4 与刷新/降级交互。** `_register_utility_tools` 也在 `_reregister_stdio_tools`（Change 5）末尾调用——刷新按前缀删 `{id}__*`（含合成工具）后，重注册 tools 再重注册合成工具，避免刷新丢失它们。降级：合成工具同 `{id}__*` 前缀，`_schema_visibility` 自动隐藏，无需额外处理。

## Risks / Trade-offs

- `read_resource(uri)`：SDK 形参标注 AnyUrl，但运行时按普通实参传入 str，由 SDK 内部构造请求时 pydantic 校验/强转，传 str 可行。
- resources/prompts 结果结构多样（资源列表/内容/消息），统一 JSON 文本化对 LLM 足够；如需更精细呈现可后续。
- 仅 scope=None 注册（与现有工具一致）；agent-scoped 的合成工具记为后续。
