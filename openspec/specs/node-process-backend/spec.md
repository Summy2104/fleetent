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

### Requirement: 容器进程后端
系统 SHALL 提供 `container` 进程后端，实现与 `local` 后端相同的 spawn / stop / is_alive 接口，但以独立容器（非 node 子进程）运行 agent，使 agent 生命周期与 node 进程/容器解耦。该后端 SHALL：

- **spawn**：经 docker 起一个 agent 容器（运行 `fleetent agent run <name> --no-im --port <fixed>`），打可识别 label（含 agent name 与 tenant），接入与 node 同一网络，挂载 per-agent home 卷。
- **stop**：触发既有优雅 drain 链（SIGUSR1 → 超时升级），不在 node 侧重复实现信号序列。
- **is_alive / 认领**：以容器运行态（按 label 查询）为真相源，使 node 重启后能认领仍在运行的 agent 容器而不重复 spawn；容器不存在或非运行态判为不存活，供 reconcile 重拉。

#### Scenario: spawn 起独立 agent 容器
- **WHEN** container 后端 spawn agentA
- **THEN** 启动一个带 agent name/tenant label 的 agent 容器，运行 `fleetent agent run`
- **AND** 容器接入 node 同一网络并挂载 agentA 的 home 卷
- **AND** is_alive 据容器运行态返回真

#### Scenario: node 重启后认领存活 agent 容器
- **WHEN** node 进程/容器重启，agentA 容器仍在运行
- **THEN** 新 node 经 label 查询认出 agentA 容器存活
- **AND** reconcile 不重复 spawn agentA（生命周期与 node 解耦）

#### Scenario: 容器消失判为不存活
- **WHEN** agentA 容器已退出或被删除
- **THEN** is_alive 返回假
- **AND** reconcile 据此重新拉起 agentA

#### Scenario: stop 经优雅 drain 停止容器
- **WHEN** container 后端 stop agentA
- **THEN** 触发 agent 既有 drain 链（SIGUSR1 起），容器优雅退出
- **AND** 不在 node 侧另写信号序列

### Requirement: 进程后端按配置选型
node SHALL 经配置项（`node.backend`，取值 `process` | `container`）选择注入哪种进程后端，缺省为 `process`（既有 local 后端），使 dev/裸机零依赖直跑、生产走容器，且旧部署行为不变。

#### Scenario: 缺省选 local 进程后端
- **WHEN** 未配置 `node.backend`
- **THEN** node 注入 local 进程后端，行为与既有一致

#### Scenario: 配置 container 选容器后端
- **WHEN** `node.backend` 配置为 `container`
- **THEN** node 注入容器进程后端

### Requirement: agent 端点解析与后端解耦
进程后端 SHALL 向 forwarder 暴露 agent 的可达端点 `(host, port)`，使 forwarder 不再硬编码 loopback 地址。local 后端 SHALL 返回 loopback host，container 后端 SHALL 返回该 agent 容器在网络内的可达 host。

#### Scenario: local 后端返回 loopback 端点
- **WHEN** forwarder 查询 agentA 端点且后端为 local
- **THEN** 返回 `127.0.0.1` 与该 agent 的 loopback 端口（行为与既有一致）

#### Scenario: container 后端返回容器网络端点
- **WHEN** forwarder 查询 agentA 端点且后端为 container
- **THEN** 返回 agentA 容器在网络内可达的 host 与端口
- **AND** forwarder 据此转发 `/chat` 与 `/ws`，不使用硬编码 `127.0.0.1`

