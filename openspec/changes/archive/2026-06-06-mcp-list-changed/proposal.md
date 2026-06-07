## Why

stdio MCP 服务可在运行时增删工具并发出 `notifications/tools/list_changed`。fleetent 在注册时抓取一份静态工具列表后就忽略该通知——服务新增/移除的工具在重启前不会反映到 agent 可见的工具表。利用已有的持久 stdio 会话（`ClientSession` 长驻于模块 `AsyncExitStack`），可在收到通知时动态刷新。

## What Changes

- 为 stdio 服务的持久 `ClientSession` 注册 message handler：收到 `tools/list_changed` 时**调度一个独立后台任务**重新发现并注册该服务工具——绝不在 handler 内联发请求（规避 hermes 实测的「在 handler 处理中向同一 stdio 流发请求导致 wedge」竞态）。
- 刷新逻辑：**identity guard**（会话已被替换则忽略陈旧通知）+ per-server 锁（合并通知风暴、去重）+ **原地重注册**（同步、无 await，对单线程事件循环里读注册表的其他协程原子，无 dict-changed-during-iteration 竞态）。
- 仅 stdio：HTTP 传输无持久 server→client 通道（需未来的 GET 流/流恢复），故 list_changed 不适用于 HTTP——记为与「Streamable HTTP 流恢复」一并做。

非破坏性：不发 list_changed 通知的服务行为不变（仍用注册时的静态列表）。

## Capabilities

### New Capabilities
- `mcp-dynamic-tools`: 定义 stdio MCP 服务在收到 `tools/list_changed` 时动态刷新其注册工具的行为与安全约束（独立任务、identity guard、去重、原地重注册）。

### Modified Capabilities
<!-- 无：现有 spec 未涉及动态工具刷新，为纯新增能力。 -->

## Impact

- 代码：`src/fleetent/integrations/mcp/client.py`——`McpServerConfig` 加 `_list_refresh_lock`；新增 `_is_tools_list_changed`/`_reregister_stdio_tools`/`_refresh_stdio_tools`/`_make_message_handler`；`_register_stdio_server` 给 `ClientSession` 传 `message_handler`。
- 行为：stdio 服务工具变更可在不重启下反映；HTTP 不变；不发通知的服务不变。
- 测试：`tests/unit/` 新增 list_changed 检测、原地重注册、刷新 identity guard/去重、handler→任务→刷新全链路（mock 会话/通知，无真实子进程）。
- 依赖/外部系统：无新增依赖（用既有 `mcp` SDK 的 `message_handler`），不触碰 `data/`。
