## ADDED Requirements

### Requirement: `fleetent agent stop` 优雅停一个本地 agent

`fleetent` CLI SHALL 提供 `agent stop <agent-id>`，对该 agent home 的运行进程执行优雅停机：复用既有 drain 协议（读 `<home>/.fleetent.pid` → SIGUSR1 排干 → 超时 SIGTERM → 再超时 SIGKILL），与 `agent restart` 的停机阶段同一实现（单一真相源）。无 pid 文件或进程已退出时 SHALL 静默成功（幂等）。该命令使 node supervisor 可经 subprocess 优雅停 agent，而无需在 node 侧重复信号逻辑、无需 import runtime 内部。

#### Scenario: 停一个在跑的 agent

- **WHEN** `fleetent agent stop support` 且其进程在跑
- **THEN** 进程经 SIGUSR1 drain 优雅退出（超时回退 SIGTERM/SIGKILL），pid 文件清理

#### Scenario: 停一个已不在跑的 agent 幂等成功

- **WHEN** `fleetent agent stop support` 但无 pid 文件或进程已退出
- **THEN** 命令静默成功，不报错
