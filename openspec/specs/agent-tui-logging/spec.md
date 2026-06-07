# agent-tui-logging

## Purpose

规范 TUI 客户端各模块（transport、backend、dispatch、app）的结构化日志输出，统一日志器命名、级别和字段约定，便于 TUI 运行时问题定位与可观测性。

## Requirements

### Requirement: tui.transport 记录 WebSocket 连接事件

`tui/transport.py` SHALL 使用 `get_logger("tui.transport")` 记录 WebSocket 连接状态。

#### Scenario: 连接建立记录 info
- **WHEN** WebSocket 连接成功建立
- **THEN** 以 `info` 级别记录，fields 包含 `url`

#### Scenario: 连接断开记录 info
- **WHEN** WebSocket 连接正常断开
- **THEN** 以 `info` 级别记录，fields 包含 `reason`

#### Scenario: 关闭出错记录 warn
- **WHEN** WebSocket 关闭过程抛出异常
- **THEN** 以 `warn` 级别记录，fields 包含 `error`

### Requirement: tui.backend 记录后端通信事件

`tui/backend.py` SHALL 使用 `get_logger("tui.backend")` 记录后端连接与帧处理异常。

#### Scenario: 重连触发记录 info
- **WHEN** 后端触发重连
- **THEN** 以 `info` 级别记录，fields 包含 `attempt`、`reason`

#### Scenario: 非法帧记录 warn
- **WHEN** 收到无法解析的 JSON 帧
- **THEN** 以 `warn` 级别记录，fields 包含 `frame_preview`（截断 200 字符）

#### Scenario: 接收协程异常退出记录 warn
- **WHEN** 接收协程因异常退出
- **THEN** 以 `warn` 级别记录，fields 包含 `error`

### Requirement: tui.dispatch 记录用户指令调度事件

`tui/dispatch.py` SHALL 使用 `get_logger("tui.dispatch")` 记录指令调度失败。

#### Scenario: run 失败记录 warn
- **WHEN** 调度一个 run 请求失败
- **THEN** 以 `warn` 级别记录，fields 包含 `run_id`、`error`

### Requirement: tui.app 记录 TUI 应用生命周期

`tui/app.py` SHALL 使用 `get_logger("tui.app")` 记录 TUI 启动与退出。

#### Scenario: TUI 启动记录 info
- **WHEN** TUI 应用主循环启动
- **THEN** 以 `info` 级别记录，fields 包含 `server_url`

#### Scenario: TUI 退出记录 info
- **WHEN** TUI 应用主循环退出
- **THEN** 以 `info` 级别记录，fields 包含 `reason`
