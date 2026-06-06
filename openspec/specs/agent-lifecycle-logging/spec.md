# agent-lifecycle-logging

## Purpose

规范 agent 生命周期平台模块（controller、materialize、api）的结构化日志输出，统一日志器命名、级别和字段约定，便于 agent 进程启停操作的审计与故障定位。

## Requirements

### Requirement: agent_lifecycle.controller 记录进程启停事件

`platform/agent_lifecycle/controller.py` SHALL 使用 `get_logger("agent_lifecycle.controller")` 记录 agent 进程的启停操作。

#### Scenario: agent 进程启动记录 info
- **WHEN** `AgentController.start()` 成功 spawn 一个 agent 进程
- **THEN** 以 `info` 级别记录，fields 包含 `name`、`pid`

#### Scenario: agent 进程停止记录 info
- **WHEN** `AgentController.stop()` 成功终止一个 agent 进程
- **THEN** 以 `info` 级别记录，fields 包含 `name`、`pid`

#### Scenario: 重复 start 记录 warn
- **WHEN** `start()` 被调用但该 agent 已有正在运行的进程
- **THEN** 以 `warn` 级别记录，fields 包含 `name`、`existing_pid`

#### Scenario: stop 时进程不存在记录 warn
- **WHEN** `stop()` 被调用但该 agent 无跟踪进程
- **THEN** 以 `warn` 级别记录，fields 包含 `name`

### Requirement: agent_lifecycle.materialize 记录物化操作结果

`platform/agent_lifecycle/materialize.py` SHALL 使用 `get_logger("agent_lifecycle.materialize")` 记录 agent home 物化的成功与失败。

#### Scenario: 物化成功记录 info
- **WHEN** agent home（agent.yaml + .env）成功写入磁盘
- **THEN** 以 `info` 级别记录，fields 包含 `name`、`path`

#### Scenario: 物化失败记录 error
- **WHEN** 物化过程抛出异常
- **THEN** 以 `error` 级别记录，fields 包含 `name`、`exception`

#### Scenario: agent.yaml 写入记录 debug
- **WHEN** agent.yaml 文件被写入
- **THEN** 以 `debug` 级别记录，fields 包含 `name`、`path`

### Requirement: agent_lifecycle.api 记录管理 API 调用

`platform/agent_lifecycle/lifecycle_admin_api.py` SHALL 使用 `get_logger("agent_lifecycle.api")` 记录 start/stop 管理接口的调用。

#### Scenario: 收到 start 请求记录 info
- **WHEN** `POST /admin/agents/<name>/start` 接口被调用
- **THEN** 以 `info` 级别记录，fields 包含 `name`

#### Scenario: 收到 stop 请求记录 info
- **WHEN** `POST /admin/agents/<name>/stop` 接口被调用
- **THEN** 以 `info` 级别记录，fields 包含 `name`

#### Scenario: 操作失败记录 warn
- **WHEN** start 或 stop 操作因 HTTP 异常失败
- **THEN** 以 `warn` 级别记录，fields 包含 `name`、`status_code`、`error`
