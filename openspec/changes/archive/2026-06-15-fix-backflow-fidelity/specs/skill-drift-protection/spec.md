## MODIFIED Requirements

### Requirement: materialize 记录 base_version

materialize 覆盖某 agent 的 skill 副本时 SHALL 在 `agent_skills.base_version` 记录该副本物化自的**池 skill 目录内容 hash（sha256）**，并 SHALL 在 `agent_skills.base_commit` 额外记录该副本物化自的**池 git commit**（该 skill 子树的版本，供回流重建 base）。`base_version`（内容 hash）始终专用于 drift 判定（home 内容是否被改动）——pool git sha 不参与 drift，故 pool 自身更新不会误判。`base_commit`（git sha）仅供回流定位 base，不参与 drift。存量行 `base_commit` 为空时下次物化 backfill。

#### Scenario: 部署写入内容 hash base_version 与 git commit base_commit
- **WHEN** agent "support-bot" 的 skill "billing"（未漂移）被 materialize 刷新
- **THEN** `agent_skills` 中该行的 `base_version` 更新为池中 "billing" 目录当前内容的 sha256 hash（64 hex），`base_commit` 更新为该 skill 在池 git 中的当前 commit

#### Scenario: pool 更新后重新物化不误判 drift
- **WHEN** pool skill "billing" 被更新（v1→v2），agent home 副本仍为 v1（未被 agent 修改）
- **THEN** 再次 materialize 检测 home_hash == base_version（均为 v1 内容 hash）→ not drifted → 正常覆盖为 v2（并刷新 base_commit）

#### Scenario: agent 修改 home 副本后判定 drift
- **WHEN** agent 修改了其 home 下 skill "crm-ops" 副本，re-materialize 运行
- **THEN** home_hash != base_version → drift=1 → home 副本被保留不覆盖（base_commit 不变，供后续回流定位 base）
