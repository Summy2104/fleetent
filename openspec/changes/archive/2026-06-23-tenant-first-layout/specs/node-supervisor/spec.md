## MODIFIED Requirements

### Requirement: 幂等 reconcile（期望↔实际）

`fleetent node start` SHALL 把期望集调谐成本地真实进程，幂等：

- 期望含某 agent ∧ 其本地未在跑 → 在 `tenants/<tenant>/agents/<agent>/` 写下发 config、env 与 skills，再经进程后端拉起。
- 某 agent 本地在跑 ∧ 不在期望集（被 disable/archive/unpin）→ 经进程后端优雅停，并擦除该 agent 的 `.env` secret scaffold。
- **实际态真相取本地 PID 文件 + 探活**，不依赖守护自身内存——故 `fleetent node start` 重启后 SHALL re-adopt 仍在跑的 agent（不重复拉起、不误杀）。
- 某 agent 期望在跑但进程已死（崩溃）→ 下一轮重新拉起。

#### Scenario: 拉起缺失的期望 agent
- **WHEN** 期望含 tenant `acme` 的 agentA 且本地无其存活进程
- **THEN** node 写 `tenants/acme/agents/agentA/agent.yaml`
- **AND** 写 `.env` 和 desired skills
- **AND** 拉起其进程

#### Scenario: 停掉不再期望的 agent
- **WHEN** agentB 本地在跑但不在本轮期望集
- **THEN** node 优雅停 agentB
- **AND** 擦除该 tenant-aware home 下的 `.env`

#### Scenario: 守护重启后 re-adopt
- **WHEN** `fleetent node start` 重启，本地 tenant-aware PID 文件显示 agentA 仍存活且仍在期望集
- **THEN** node 不重复拉起 agentA、不杀它

#### Scenario: 崩溃的期望 agent 被重拉
- **WHEN** agentA 在期望集但其 PID 文件对应进程已不存活
- **THEN** 下一轮 reconcile 重新拉起 agentA

## ADDED Requirements

### Requirement: Node deploys skill bundles atomically

node SHALL 根据 desired-state skill manifest 下载缺失或过期的 skill bundle，校验 `bundle_sha256`，安全解压到临时目录，再原子替换 `skills/<skill>/`。node MUST NOT 直接访问 Git 仓库。

#### Scenario: Missing skill is deployed
- **WHEN** desired-state 要求 skill `foo` 的 `base_version=abc`，本地没有该版本
- **THEN** node 从 manifest 的 bundle URL 下载 bundle
- **AND** 校验 hash 后部署到 agent home `skills/foo/`
- **AND** 记录本地部署的 `base_version` 与 `base_commit`

#### Scenario: Existing matching skill is skipped
- **WHEN** 本地 `skills/foo/` 已记录 `base_version=abc`
- **THEN** node 不重新下载或覆盖该 skill

#### Scenario: Drifted skill is not overwritten
- **WHEN** 本地 `skills/foo/` 已 drift
- **THEN** node 不用 desired bundle 覆盖该目录
- **AND** 在 status 中上报 drift

#### Scenario: Unsafe bundle is rejected
- **WHEN** 下载的 bundle 含绝对路径、`..`、`.git`、symlink/hardlink 逃逸或 hash 不匹配
- **THEN** node 拒绝部署
- **AND** 不修改当前 agent home skill 副本
