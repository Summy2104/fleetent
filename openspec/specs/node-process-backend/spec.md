# node-process-backend Specification

## Purpose
TBD - created by archiving change node-supervisor. Update Purpose after archive.
## Requirements
### Requirement: 可插拔进程后端接口

系统 SHALL 定义 `fleetent node start` 用于启停/探活本地 agent 进程的进程后端接口（spawn / stop / is_alive），使 reconcile 逻辑与"具体怎么跑进程"解耦。后端经能力/选型注入（仿 sandbox 后端范式），v1 提供 `local` 实现；systemd 等后端列 roadmap、不在本 change。

#### Scenario: reconcile 经接口而非具体后端操作进程

- **WHEN** reconcile 需要拉起/停止/探活某 agent
- **THEN** 它调用进程后端接口方法，不直接耦合具体实现

### Requirement: local 进程后端

`local` 后端 SHALL：

- **spawn**：以 subprocess 启动 `fleetent agent run <agent-home-key>`（沿用 runtime 既有 home 约定与 PID 文件 `<home>/.fleetent.pid`）。
- **stop**：经 subprocess 调用 `fleetent agent stop <agent-home-key>`（优雅 drain，见 `agent-runtime-cli`），不在 node 侧重复实现信号序列。
- **is_alive**：读 `<home>/.fleetent.pid` + `os.kill(pid, 0)` 探活——真相在 PID 文件而非守护内存（支撑 re-adopt）；stale PID（文件在但进程已死）SHALL 判为不存活。

#### Scenario: spawn 后产生可探活进程

- **WHEN** local 后端 spawn agentA
- **THEN** agentA 进程启动并写出 `<home>/.fleetent.pid`，随后 is_alive 返回真

#### Scenario: stop 经 CLI 优雅停

- **WHEN** local 后端 stop agentA
- **THEN** 经 `fleetent agent stop` 触发 drain，进程优雅退出，PID 文件清理

#### Scenario: stale PID 判为不存活

- **WHEN** `<home>/.fleetent.pid` 存在但对应进程已不在
- **THEN** is_alive 返回假（供 reconcile 据此重拉）

