## ADDED Requirements

### Requirement: fleetent node start 守护与配置

系统 SHALL 提供新部署件 `fleetent node start`（新 console-script），作为跑在每个 agent host 上的长驻守护。它 SHALL 从环境/配置读取：platform 基址、本 node 的 node-id、node service key（`ma-<hex>`）、`FLEETENT_HOME`、reconcile 轮询间隔。`fleetent node start` SHALL 作为 platform HTTP API 的客户端运行，SHALL NOT `import fleetent.platform.*`，SHALL NOT `import` agent runtime 内部实现（仅经 subprocess 调用 agent CLI）。

#### Scenario: 守护启动并周期 reconcile

- **WHEN** `fleetent node start` 以有效配置启动
- **THEN** 它进入循环：按间隔拉取期望态 → reconcile → 上报实际态

#### Scenario: 缺失必需配置则拒绝启动

- **WHEN** 未提供 node-id 或 service key 或 platform 基址
- **THEN** `fleetent node start` 报错退出，不进入循环

### Requirement: 拉取分区期望态（platform-api provider + 本地缓存）

`fleetent node start` SHALL 经 `GET /nodes/{node-id}/desired-state` 拉取期望态（携带 `Authorization: Bearer <node service key>`），解析响应 `{node_id, agents:[{agent_id, name, config}]}`。期望态来源 SHALL 经可插拔 provider（v1 为 platform-api）。每次成功拉取 SHALL 缓存到 node 本地；当 platform 暂不可达时，SHALL 用最近一次缓存继续 reconcile（避免 platform 短暂下线即停摆）。

#### Scenario: 正常拉取并解析

- **WHEN** platform 返回两个 enabled agent
- **THEN** node 得到两个 (agent_id, name, config) 条目，作为本轮期望集

#### Scenario: platform 不可达时回落缓存

- **WHEN** 拉取失败但存在上一次缓存
- **THEN** node 用缓存的期望集继续 reconcile，并记录拉取失败；缓存缺失时本轮跳过且不误停在跑的 agent

### Requirement: 幂等 reconcile（期望↔实际）

`fleetent node start` SHALL 把期望集调谐成本地真实进程，幂等：

- 期望含某 agent ∧ 其本地未在跑 → 写下发 `config` 到本地 agent home，再经进程后端拉起。
- 某 agent 本地在跑 ∧ 不在期望集（被 disable/archive/unpin）→ 经进程后端优雅停。
- **实际态真相取本地 PID 文件 + 探活**，不依赖守护自身内存——故 `fleetent node start` 重启后 SHALL re-adopt 仍在跑的 agent（不重复拉起、不误杀）。
- 某 agent 期望在跑但进程已死（崩溃）→ 下一轮重新拉起。

#### Scenario: 拉起缺失的期望 agent

- **WHEN** 期望含 agentA 且本地无其存活进程
- **THEN** node 写 agentA 的 config 到本地 home 并拉起其进程

#### Scenario: 停掉不再期望的 agent

- **WHEN** agentB 本地在跑但不在本轮期望集
- **THEN** node 优雅停 agentB

#### Scenario: 守护重启后 re-adopt

- **WHEN** `fleetent node start` 重启，本地 PID 文件显示 agentA 仍存活且仍在期望集
- **THEN** node 不重复拉起 agentA、不杀它

#### Scenario: 崩溃的期望 agent 被重拉

- **WHEN** agentA 在期望集但其 PID 文件对应进程已不存活
- **THEN** 下一轮 reconcile 重新拉起 agentA

### Requirement: config-hash 漂移触发优雅重启

`fleetent node start` SHALL 记录每个在跑 agent 已应用配置的 hash；当期望态下发的 `config` hash 与在跑的不一致时，SHALL 优雅停后用新配置重拉（agent 进程 home-driven、boot 时读配置，无热重载）。

#### Scenario: 配置变更后重启

- **WHEN** agentA 在跑，期望态返回的 config hash 与已应用的不同
- **THEN** node 优雅停 agentA、写新 config、重新拉起

#### Scenario: 配置未变不重启

- **WHEN** 期望态 config hash 与在跑的一致
- **THEN** node 不动该 agent

### Requirement: 上报实际态

`fleetent node start` SHALL 每轮经 `POST /nodes/{node-id}/status` 上报本地各 agent 的实际态 `{agents:[{agent_id, phase, pid?, health?, detail?}]}` 与心跳。上报为只读投影，不影响本地控制决策（控制真相在 PID 文件）。

#### Scenario: 上报在跑 agent

- **WHEN** 本轮 agentA 在跑(pid=123)
- **THEN** node POST 上报 agentA phase=running、pid=123

#### Scenario: 上报失败不影响本地 reconcile

- **WHEN** 上报请求失败
- **THEN** node 记录失败但本地进程不受影响，下轮重试
