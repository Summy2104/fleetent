# skill-drift-protection Specification

## Purpose
TBD - created by archiving change redesign-skill-schema-drift-protection. Update Purpose after archive.
## Requirements
### Requirement: 重新部署保留已漂移的 agent skill 副本

`materialize` 将池 skill 镜像进 agent home 时 SHALL 按 skill 子目录粒度判定：当某 `(agent, skill)` 的 `agent_skills.drift = 1` 时，平台 SHALL **不覆盖**该 agent home 下对应的 skill 子目录（保住运行时进化但未回流的内容），并 SHALL 记审计日志；`drift = 0` 时 SHALL 正常覆盖该子目录。

#### Scenario: 漂移副本不被覆盖
- **WHEN** agent "support-bot" 的 skill "crm-ops" 在 `agent_skills` 中 `drift=1`，触发该 agent 重新 materialize
- **THEN** `home/agents/support-bot/skills/crm-ops/` 不被池版本覆盖，进化内容保留
- **AND** 写一条「保护跳过覆盖」的审计日志

#### Scenario: 未漂移副本正常刷新
- **WHEN** agent "support-bot" 的 skill "billing" 在 `agent_skills` 中 `drift=0`，触发重新 materialize
- **THEN** `home/agents/support-bot/skills/billing/` 被池版本正常覆盖刷新

#### Scenario: 子目录粒度不连带冻结
- **WHEN** 同一 agent 下 "crm-ops" 漂移而 "billing" 未漂移，触发 materialize
- **THEN** "crm-ops" 被保护、"billing" 被刷新，互不影响

### Requirement: drift 由平台单向判定，agent 运行时不反写

per-agent drift SHALL 由平台侧判定与写入：平台 SHALL 通过**读取** agent home 副本的产物（agent 侧 `write_skill` 注入 SKILL.md frontmatter 的运行时写入痕迹，或与 `base_version` 对应池内容的哈希比对）来判定漂移，并写入平台自己的 `agent_skills.drift` / `drift_at`。agent 运行时 SHALL NOT 写入任何平台表（核心架构契约）。

#### Scenario: 平台读 agent 产物判定漂移
- **WHEN** agent 运行时经 reflection 修改了自己 home 下的某 skill 副本
- **THEN** 平台读取该 home 副本的产物后将对应 `(agent, skill)` 的 `drift` 置为 1、记录 `drift_at`
- **AND** 该写入由平台完成，agent 运行时未直接写任何平台表

#### Scenario: 无 platform 环境下 agent 运行不受影响
- **WHEN** 在没有 platform、平台 DB 表不存在的环境下运行 `fleetent agent run` 并修改本地 skill
- **THEN** agent 正常运行，不尝试写 drift，对话可完成

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
