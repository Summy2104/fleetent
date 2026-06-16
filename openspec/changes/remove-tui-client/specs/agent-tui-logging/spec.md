## REMOVED Requirements

### Requirement: tui.backend 记录后端通信事件

**Reason**: 终端 TUI 客户端被移除，`tui/backend.py`（客户端 WS 连接后端）随之删除，该模块的日志要求不再适用。
**Migration**: 无替代。多轮交互改用网页后台聊天（`/admin/chat/*`）或 IM 渠道；`/ws` 服务端的连接/帧处理日志由保留的 `tui.transport`、`tui.dispatch` 要求继续覆盖。

### Requirement: tui.app 记录 TUI 应用生命周期

**Reason**: 终端 TUI 客户端被移除，`tui/app.py`（prompt_toolkit 主循环）随之删除，TUI 应用生命周期日志要求不再适用。
**Migration**: 无替代。`fleetent-tui` 命令不再存在；agent 进程生命周期日志由 `agent-runtime-cli` / `agent-runtime-logging` 覆盖。

<!-- 保留不动：`tui.transport`、`tui.dispatch` —— 对应模块是 /ws 网关服务端共用实现，仍然存在，日志要求继续有效，故不在本 delta 中。 -->
