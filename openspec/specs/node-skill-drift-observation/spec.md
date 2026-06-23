# node-skill-drift-observation Specification

## Purpose
TBD - created by archiving change tenant-first-layout. Update Purpose after archive.
## Requirements
### Requirement: Node observes skill drift from real agent home

managed 模式下 node SHALL 扫描自己拥有的 agent home skill 副本，计算每个 skill 的 home content hash，并与 desired-state 中的 `base_version` 对比；若内容不同或存在 runtime provenance，node SHALL 将该 skill 标记为 drifted。

#### Scenario: Modified home skill is reported drifted
- **WHEN** agent home 中 `skills/foo/` 的内容 hash 与 desired-state 的 `base_version` 不同
- **THEN** node 上报 `foo` 的 `drift=true`
- **AND** 上报包含 `home_hash`、`base_version`、`base_commit` 与 agent 标识

#### Scenario: Runtime provenance is a drift signal
- **WHEN** agent home 中某 skill 的 `SKILL.md` 含运行时写入 provenance
- **THEN** node 上报该 skill `drift=true`

### Requirement: Platform stores node-observed skill deployment state

platform SHALL 接收 node 上报的 skill deployment observation，并把 drift/base/home hash 等状态关联到对应 `agent_skills` 绑定或等价治理投影。platform MUST treat this as node observation, not as evidence from a platform-local home copy.

#### Scenario: Status update marks agent skill drift
- **WHEN** node status payload 上报 agent `A` 的 skill `foo` drifted
- **THEN** platform 将 `A/foo` 的治理状态标记为 drifted
- **AND** 记录最近观测的 node 与时间

### Requirement: Backflow nomination fetches bundle from owning node

backflow nomination SHALL 从该 agent placement 的 owning node 拉取真实 home skill bundle；platform MUST NOT 从 `paths.agent_home_dir(...)` 读取本机 materialized home 作为 managed agent 的 proposed bundle。

#### Scenario: Nominate reads real node home
- **WHEN** admin 对 managed agent 的 drifted skill 发起 backflow nomination
- **THEN** platform 查询该 agent 的 owning node
- **AND** 通过 node 受控 endpoint 获取该 skill 的真实 home bundle
- **AND** 用返回 bundle 创建 `backflow_proposals.proposed_bundle`

#### Scenario: Missing owning node prevents nomination
- **WHEN** drifted skill 没有 active placement 或 owning node 不可达
- **THEN** nomination fail loud
- **AND** 不创建基于 stale platform-local 文件的 backflow proposal

### Requirement: Node skill bundle read endpoint is constrained

node 提供给 platform 的 skill bundle read endpoint MUST 只允许读取该 node 拥有的 `tenants/<tenant>/agents/<agent>/skills/<skill>/` 子树，MUST 拒绝绝对路径、`..`、`.git` 与链接逃逸。

#### Scenario: Path escape is rejected
- **WHEN** platform 请求的 skill bundle 路径会逃逸 agent skill 目录
- **THEN** node 拒绝请求
- **AND** 不返回任何文件内容

