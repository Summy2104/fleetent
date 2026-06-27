## ADDED Requirements

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
