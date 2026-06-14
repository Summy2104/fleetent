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

materialize 覆盖某 agent 的 skill 副本时 SHALL 在 `agent_skills.base_version` 记录该副本物化自的池版本，作为后续回流（未来 change）的基准。

#### Scenario: 部署写入 base_version
- **WHEN** agent "support-bot" 的 skill "billing"（`drift=0`）被 materialize 刷新
- **THEN** `agent_skills` 中该行的 `base_version` 更新为当前 `skills.current_version`

