## Context

stdio 服务的 `ClientSession` 长驻 `_active_sessions[(scope, id)]`（模块 `AsyncExitStack`）。MCP SDK `ClientSession(read, write, message_handler=...)` 支持 server→client 消息回调；`ToolListChangedNotification.method == "notifications/tools/list_changed"`，经 `ServerNotification.root` 投递。HTTP 传输每次调用开新 httpx，无持久 server→client 通道，故 list_changed 不适用于 HTTP。

## Goals / Non-Goals

**Goals:**
- stdio 收到 list_changed 时动态刷新注册工具（增/删），无需重启。
- 安全：独立任务刷新、identity guard、去重、原地重注册（无竞态）。

**Non-Goals:**
- HTTP list_changed（需 GET 流/流恢复，记为未来一并做）。
- prompts/resources 的 list_changed（本程序 resources/prompts 为合成工具，见 Change 6；其动态刷新可后续）。
- 不引入 RPC 全序列化锁（SDK 已按 request id 多路复用并发调用）。

## Decisions

**D1 独立任务刷新，绝不内联。** message handler 检测到 list_changed 后 `asyncio.create_task(_refresh_stdio_tools(...))`（与既有 `_schedule_reconnect` 同款 fire-and-forget），而非在 handler 内直接 `list_tools`——后者会在 handler 仍占用 stdio 读循环时向同一流发请求，造成 hermes 实测的 wedge。

**D2 identity guard + per-server 去重锁。** `_refresh_stdio_tools(server, scope, session)` 先校验 `_active_sessions.get((scope,id)) is session`（陈旧会话的通知忽略），再 `server._list_refresh_lock`（locked 则直接返回，合并通知风暴）。锁内再次校验 identity。

**D3 原地重注册、同步原子。** `_reregister_stdio_tools` 是**同步**函数（删 `{id}__*` 旧条目 + 重注册新列表，全程无 await）。asyncio 单线程协作式调度下，无 await 即不让出，故与 `get_schemas` 等同步读注册表的协程**不可能交错**——无 dict-changed-during-iteration 竞态。仅 scope=None 进共享注册表（与现有注册一致；agent-scoped 工具经 call_tool(scope) 派发，不在共享表）。工具 call 闭包在调用时动态查 `_active_sessions`，故替换注册表条目不影响在途调用。

**D4 检测用 method 字符串、不硬绑类型。** `_is_tools_list_changed(msg)` 读 `getattr(getattr(msg,"root",None),"method",None) == "notifications/tools/list_changed"`，对 SDK 类型变动稳健。

## Risks / Trade-offs

- handler 中 `create_task` fire-and-forget（与既有 reconnect 一致）；任务异常在 `_refresh_stdio_tools` 内 best-effort，不影响读循环。
- 仅刷新 scope=None 共享注册表；agent-scoped 动态刷新记为后续（与现有 agent-scoped 注册局限一致）。
- list_changed 风暴 → 锁去重 + identity guard，至多一个在途刷新。
