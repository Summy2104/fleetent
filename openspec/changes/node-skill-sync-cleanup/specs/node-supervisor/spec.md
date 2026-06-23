## MODIFIED Requirements

### Requirement: 幂等 reconcile（期望↔实际）

`fleetent node start` SHALL 把期望集调谐成本地真实进程，幂等：

- 期望含某 agent ∧ 其本地未在跑 → 写下发 `config` 到本地 agent home，再经进程后端拉起。
- 某 agent 本地在跑 ∧ 不在期望集（被 disable/archive/unpin）**∧ 期望态来自权威 `remote` 源** → 经进程后端优雅停（并按「node 删除已移除 agent 的本地文件（权威态）与缓存安全」清理其本地 home）。期望态来自 `cache` 回落源时，disappear 的 agent MUST NOT 被停或删（见该要求）。
- **实际态真相取本地 PID 文件 + 探活**，不依赖守护自身内存——故 `fleetent node start` 重启后 SHALL re-adopt 仍在跑的 agent（不重复拉起、不误杀）。
- 某 agent 期望在跑但进程已死（崩溃）→ 下一轮重新拉起。

#### Scenario: 拉起缺失的期望 agent

- **WHEN** 期望含 agentA 且本地无其存活进程
- **THEN** node 写 agentA 的 config 到本地 home 并拉起其进程

#### Scenario: 停掉不再期望的 agent（权威态）

- **WHEN** agentB 本地在跑但不在本轮**权威 `remote`** 期望集
- **THEN** node 优雅停 agentB

#### Scenario: 守护重启后 re-adopt

- **WHEN** `fleetent node start` 重启，本地 PID 文件显示 agentA 仍存活且仍在期望集
- **THEN** node 不重复拉起 agentA、不杀它

#### Scenario: 崩溃的期望 agent 被重拉

- **WHEN** agentA 在期望集但其 PID 文件对应进程已不存活
- **THEN** 下一轮 reconcile 重新拉起 agentA

## ADDED Requirements

### Requirement: node 同步 per-agent skill 文件与变更重启

`fleetent node start` 在 reconcile materialize 某期望 agent 的 home（写 `agent.yaml`）时，SHALL 把该 agent 期望态携带的 skill 文件落到 `<home>/agents/<name>/skills/<skill>/...`——即 agent 进程启动时 `scan` 的目录（agent 固定读 `<home>/skills`、不读 `FLEETENT_SKILLS_DIR`，故 node SHALL NOT 依赖注入该环境变量）。落盘 SHALL 在 `backend.spawn` **之前**完成。

node SHALL 维护一份 per-agent skill manifest（记录其落盘的各 skill 名与版本）判定 skill 的增/删/改：

- skill 集合或某 skill 版本相对 manifest 变化时（即便 `config` hash 未变）→ SHALL 优雅停后用新 skill 文件重拉（agent 无热重载、boot 时读 skill）。
- 期望态不再含的 skill（manifest 有、desired 无）→ SHALL 清理其 skill 目录并更新 manifest。
- node 的 skill 清理 SHALL 只删自己 manifest 记录过的 skill，MUST NOT 删除 builtin skill 或 operator 自留的 skill；同名平台 skill 被清理后，builtin 经 agent 侧从包内目录的 scan 自动回退、不丢失。

#### Scenario: materialize 时落盘 skill 文件

- **WHEN** node reconcile 拉起一个期望态携带 skill `alpha` 的 agent
- **THEN** `<home>/agents/<name>/skills/alpha/` 出现 `alpha` 的全部文件（内容与下发一致），manifest 记录 `alpha` 及其版本
- **AND** skill 文件在 agent 进程 `spawn` 前已就位

#### Scenario: skill 版本变更触发重启

- **WHEN** 某在跑 agent 的 `config` hash 未变，但期望态中某 skill 的版本与 manifest 记录不同
- **THEN** node 优雅停该 agent、重写 skill 文件、再重拉

#### Scenario: skill 未变不重启

- **WHEN** 某在跑 agent 的 `config` hash 与 skill 集合/版本均与已应用的一致
- **THEN** node 不停不重拉该 agent

#### Scenario: 移除的 skill 被清理且不误删 builtin

- **WHEN** 期望态移除了 agent 此前绑定的 skill `alpha`，而该 agent 的 skills 目录下另有一个非 node 管理的目录（不在 manifest 中）
- **THEN** node 删除 `alpha` 的目录并更新 manifest
- **AND** 那个非 node 管理的目录保持不变

### Requirement: node 删除已移除 agent 的本地文件（权威态）与缓存安全

`fleetent node start` 对「本地存在但已从**权威 `remote`** 期望态消失」的 agent，SHALL 在停其进程后删除其本地 home 目录 `<home>/agents/<name>` 并从已应用配置 hash 账本移除该条目，避免 orphan 目录被持续重列、账本无限增长。停进程步骤 SHALL 舱壁化——stop 失败（如进程已死）只记日志、不传播、不阻断后续删除与本轮其它 agent 的 reconcile / 状态上报。

当期望态来自 `cache` 回落源（platform 不可达）时，node MUST NOT 因某 agent 不在（可能过期/为空的）缓存期望集而停它或删其文件——避免 platform 短暂下线即误停/误删健康 agent。

#### Scenario: 权威态删除已移除 agent 的 home

- **WHEN** agentB 本地在跑、其 home 存在，但不在本轮 `remote` 期望集
- **THEN** node 停 agentB 后删除 `<home>/agents/agentB` 目录，并从 hash 账本移除 agentB 条目

#### Scenario: 缓存回落态不误停不误删

- **WHEN** 本轮期望态来自 `cache` 回落源，某本地在跑 agent 不在该缓存期望集
- **THEN** node MUST NOT 停该 agent，MUST NOT 删其 home 目录（进程与文件保留）

#### Scenario: 删除时 stop 失败被舱壁化

- **WHEN** 删除某已移除 agent 时其 `stop` 抛错（如进程已不存在）
- **THEN** node 记录该失败但不传播异常，仍删除其 home 目录，且本轮其它 agent 的 reconcile 与状态上报不受影响
