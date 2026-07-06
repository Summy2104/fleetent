## MODIFIED Requirements

### Requirement: 回流提名先推备份分支保命

启用外部 git 源时，平台 SHALL 经一个独立定时任务（`backflow_pr_sweep`，类比 KB connector sweep）扫描 pending 且未备份的回流提案，把其进化副本经 `push_branch` 推到一个**备份分支** `<branch_prefix>/<agent_id>/<skill>`（**非权威主分支**），并标记 `pr_state="backed_up"`。备份是即时保命动作：即使后续 PR 被拒/关，备份分支仍留痕、agent 改动不丢。提名（`backflow_store.nominate`）与 node 上报路径 SHALL 只存 bundle、**零 git 依赖**（SHALL NOT 在 node 上报/reconcile 路径触发任何 git 操作）。分支名 SHALL 按 `(agent, skill)` 稳定，配合去重压制短命分支。

若外部源额外配置了 `skills_subdir`（见 `skill-git-sync`），`push_branch` 推送内容在备份分支中的树路径 SHALL 为 `<skills_subdir>/<name>` 而非 `<name>`，使备份分支与权威仓库的目录布局一致（人工合并到 main 时 skill 落在正确子目录下）。未配置 `skills_subdir` 时，树路径退化为 `<name>`，与本 change 之前完全一致。fork 场景（`backflow_api._fork_via_pr`）的 fork 分支同样按此规则加前缀。

#### Scenario: 提名后推备份分支

- **WHEN** sweep 扫到一条 pending 未备份的回流提案
- **THEN** 经 `push_branch` 推一个非主分支的备份分支，提案标 `pr_state="backed_up"`，记录分支名

#### Scenario: 提名与 node 上报零 git

- **WHEN** node 上报某 agent 的 skill 漂移触发自动提名
- **THEN** 提名只存 bundle，node 上报/reconcile 路径不触发任何 git_platform / push 调用

#### Scenario: 配置 skills_subdir 时备份分支内容落在子目录

- **WHEN** 外部源配置了 `skills_subdir="skills"`，sweep 把 skill "crm-ops" 的进化副本推备份分支
- **THEN** 备份分支上该内容的树路径为 `skills/crm-ops`，而非仓库根的 `crm-ops`

#### Scenario: 未配置 skills_subdir 时树路径不变

- **WHEN** 外部源未配置 `skills_subdir`
- **THEN** 备份分支/fork 分支上内容的树路径仍为 `<name>`，行为与本 change 之前一致
