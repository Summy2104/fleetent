## MODIFIED Requirements

### Requirement: accept 更新池并清 drift

审批 accept 时平台 SHALL 经 git PR 落地进化副本，而非直写池：先 `merge_pull_request` 合并该提案的 PR 到权威分支，再**复用入站 `pool_sync.align_pool_to_remote`**（fetch + reset --hard）把本地池对齐主线，使该 skill 的 `current_version` 前移到合并后的 commit；随后清除来源 `(agent, skill)` 的 drift 并 `bump_resync_epoch`，其余绑定该 skill 的 agent 在常规重新物化时拿到新版本。SHALL NOT 再 `_write_bundle_atomic` + `commit_pool` 直写池（与入站「外部 git 为权威、reset 会丢弃直写」冲突）。合并或对齐失败 SHALL 幂等重试（merge 对已合并 PR 幂等）：对齐失败时 SHALL NOT bump epoch、保留 pending + hint。

#### Scenario: accept 合并 PR 后对齐池
- **WHEN** 运营 accept 一条已开 PR 的回流提案（无冲突）
- **THEN** 平台合并该 PR，经 `align_pool_to_remote` 把池对齐主线，"crm-ops" 的 `current_version` 前移、来源 agent 的 drift 被清、`resync_epoch` 前移，且**不**经直写池产生本地 commit

#### Scenario: accept 后他 agent 拿到新版本
- **WHEN** accept 后另一个未漂移地绑定 "crm-ops" 的 agent 重新物化
- **THEN** 该 agent 拿到合并 + 对齐后的新池版本

#### Scenario: 合并成功但对齐失败不误清状态
- **WHEN** PR 已合并但 `align_pool_to_remote` 失败
- **THEN** 不 bump epoch、提案留 pending + hint、可幂等重试，SHALL NOT 误报成功

### Requirement: reject 丢弃回流

审批 reject 时平台 SHALL `close_pull_request` 关闭该提案的 PR（若已开），池不变；并清除来源 `(agent, skill)` 的 drift（使该副本下次物化被池版本覆盖）+ `bump_resync_epoch`；动作 SHALL 被审计。备份分支（若已推）SHALL 保留留痕，SHALL NOT 强制删除（agent 改动可追溯）。

#### Scenario: reject 关 PR 后副本将被覆盖
- **WHEN** 运营 reject skill "crm-ops" 的回流
- **THEN** 该提案的 PR 被关闭、池不变、该 agent 的 drift 被清、`resync_epoch` 前移，下次物化其 "crm-ops" 副本被池版本覆盖；备份分支保留

### Requirement: fork 落新命名 skill 不覆盖权威

审批 fork 时平台 SHALL 把进化副本的**完整 bundle** 作为**新命名 skill** 推一个 fork 分支并经 PR 合并到权威分支（合并后复用 `align_pool_to_remote` 对齐池），将来源 agent 的绑定指向该 fork skill，原 skill resync；SHALL NOT 覆盖原权威 skill。

#### Scenario: fork 经分支 + PR 落新命名 skill
- **WHEN** 运营对多文件 skill "crm-ops" 的回流选择 fork
- **THEN** 平台推一个新命名 skill（如 "crm-ops-support-bot"）的分支并合并、经对齐落入池，原 "crm-ops" 权威版不变，来源 agent 绑定指向 fork、原 skill resync

## ADDED Requirements

### Requirement: 回流提名先推备份分支保命

平台 SHALL 经一个独立定时任务（`backflow_pr_sweep`，类比 KB connector sweep）扫描 pending 且未备份的回流提案，把其进化副本经 `push_branch` 推到一个**备份分支** `<branch_prefix>/<agent>/<skill>`（**非权威主分支**），并标记 `pr_state="backed_up"`。备份是即时保命动作：即使后续 PR 被拒/关，备份分支仍留痕、agent 改动不丢。提名（`backflow_store.nominate`）与 node 上报路径 SHALL 只存 bundle、**零 git 依赖**（SHALL NOT 在 node 上报/reconcile 路径触发任何 git 操作）。分支名 SHALL 按 `(agent, skill)` 稳定，配合去重压制短命分支。

#### Scenario: 提名后推备份分支
- **WHEN** sweep 扫到一条 pending 未备份的回流提案
- **THEN** 经 `push_branch` 推一个非主分支的备份分支，提案标 `pr_state="backed_up"`，记录分支名

#### Scenario: 提名与 node 上报零 git
- **WHEN** node 上报某 agent 的 skill 漂移触发自动提名
- **THEN** 提名只存 bundle，node 上报/reconcile 路径不触发任何 git_platform / push 调用

### Requirement: 定时或手动开 PR

对已备份且配置 `auto_open_pr` 开启的提案，sweep SHALL 经 `open_pull_request` 从备份分支开 PR 到权威分支并标 `pr_state="pr_open"`（记录 pr_id/url）。平台 SHALL 另暴露 `POST /admin/skills/backflow/{id}/open-pr`（admin 手动对单提案开 PR）与 `POST /admin/skills/backflow/sync-backflow`（admin 手动触发整轮 sweep）。

#### Scenario: auto 开 PR
- **WHEN** sweep 扫到一条已备份、`auto_open_pr` 开启的提案
- **THEN** 从备份分支开 PR、提案标 `pr_state="pr_open"`、记录 pr_id/url

#### Scenario: 手动开 PR 与手动同步
- **WHEN** admin 调 `POST /admin/skills/backflow/{id}/open-pr` 或 `POST /admin/skills/backflow/sync-backflow`
- **THEN** 前者对该提案立即开 PR，后者立即触发一轮 sweep

### Requirement: git 不可达降级不误改治理状态

回流 sweep 与治理端点的所有 git 操作 SHALL 舱壁化：git 不可达（`GitPlatformUnavailable`）时 SHALL 标 `pr_state="deferred"` 下轮/手动重试，治理端点 SHALL 返回 503，且 SHALL NOT 改动 drift / resync_epoch（避免「以为成功实则未落地」）。单次 git 失败 SHALL NOT 崩溃定时任务、webhook 线程或服务启动。

#### Scenario: sweep 遇 git 不可达降级
- **WHEN** sweep 推分支/开 PR 时远端不可达
- **THEN** 提案标 `pr_state="deferred"`、不抛、下轮重试，其它提案与维护任务不受影响

#### Scenario: accept 时 git 不可达不误清 drift
- **WHEN** accept 调用 merge 时远端不可达
- **THEN** 端点返回 503、提案标 deferred、drift 与 resync_epoch 不变，可重试
