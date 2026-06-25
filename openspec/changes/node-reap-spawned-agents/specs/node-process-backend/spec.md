## MODIFIED Requirements

### Requirement: local 进程后端

`local` 后端 SHALL：

- **spawn**：以 subprocess 启动 `fleetent agent run <agent-home-key>`（沿用 runtime 既有 home 约定与 PID 文件 `<home>/.fleetent.pid`）。后端 SHALL 保留所启动子进程的句柄，使 node 作为父进程能够回收（reap）其退出的子进程，避免僵尸（defunct）进程累积。
- **stop**：经 subprocess 调用 `fleetent agent stop <agent-home-key>`（优雅 drain，见 `agent-runtime-cli`），不在 node 侧重复实现信号序列。stop SHALL 在停止后回收并清理该 agent 的本地子进程句柄。
- **is_alive**：以 `<home>/.fleetent.pid` 为真相源（支撑 node 重启后 re-adopt）。SHALL 将以下三种情况判为**不存活**：①PID 文件不存在；②stale PID（文件在但进程已不存在，`os.kill(pid, 0)` 抛 `ProcessLookupError`）；③**已退出但尚未被回收的僵尸子进程**——对本 node 启动的子进程，`os.kill(pid, 0)` 成功**不足以**判定存活，后端 SHALL 先对其句柄做非阻塞回收并依据退出码判定（已退出 → 不存活）。退出码判定 SHALL 优先于 `os.kill` 探活，从而同时消除 PID 复用导致的误判。

> 设计意图：被 kill 或自行崩溃的 agent 子进程在父进程（node）回收前处于僵尸态，`os.kill(pid, 0)` 对僵尸返回成功；若仅凭此判活，reconcile 的重拉分支永不触发、崩溃 agent 不自愈。回收子进程后僵尸消失，存活判定恢复真实。node 重启后无句柄的 re-adopt 路径不受影响：旧子进程已被 init 回收，`os.kill` 探活准确。

#### Scenario: spawn 后产生可探活进程

- **WHEN** local 后端 spawn agentA
- **THEN** agentA 进程启动并写出 `<home>/.fleetent.pid`，随后 is_alive 返回真
- **AND** 后端保留 agentA 子进程句柄以备回收

#### Scenario: stop 经 CLI 优雅停

- **WHEN** local 后端 stop agentA
- **THEN** 经 `fleetent agent stop` 触发 drain，进程优雅退出，PID 文件清理
- **AND** 后端回收并清除 agentA 的本地子进程句柄

#### Scenario: stale PID 判为不存活

- **WHEN** `<home>/.fleetent.pid` 存在但对应进程已不在
- **THEN** is_alive 返回假（供 reconcile 据此重拉）

#### Scenario: 已退出/僵尸子进程判为不存活

- **WHEN** 本 node 启动的 agentA 子进程已退出但尚未被回收（僵尸），`os.kill(pid, 0)` 仍成功
- **THEN** is_alive 对其句柄做非阻塞回收，依据退出码判定为不存活，返回假
- **AND** reconcile 据此重新拉起 agentA

#### Scenario: PID 复用不误判

- **WHEN** 本 node 启动的 agentA 子进程已退出（句柄退出码已置），其原 PID 被系统复用给无关进程，`os.kill(pid, 0)` 对新进程成功
- **THEN** is_alive 依据句柄退出码判定为不存活，返回假（不被复用 PID 误导）
