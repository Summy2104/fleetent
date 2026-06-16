# agent-lifecycle-logging

## Purpose

规范 agent 生命周期平台模块（controller、materialize、api）的结构化日志输出，统一日志器命名、级别和字段约定，便于 agent 进程启停操作的审计与故障定位。
## Requirements
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

