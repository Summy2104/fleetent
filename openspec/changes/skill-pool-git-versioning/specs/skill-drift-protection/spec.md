## MODIFIED Requirements

### Requirement: materialize 记录 base_version

materialize 覆盖某 agent 的 skill 副本时 SHALL 在 `agent_skills.base_version` 记录该副本物化自的**池版本 git 标识**（不再是 content-hash）。存量以 content-hash 写入的 `base_version` SHALL 平滑过渡：首次升级后物化某 `(agent, skill)` 时，若 `base_version` 无法解析为本池 git 对象，平台 SHALL 回退内容比对判定 drift（不因「content-hash ≠ git 标识」误判 drift）并将 `base_version` re-baseline 为当前 git 标识。

#### Scenario: 部署写入 git 标识 base_version
- **WHEN** agent "support-bot" 的 skill "billing"（未漂移）被 materialize 刷新
- **THEN** `agent_skills` 中该行的 `base_version` 更新为池中 "billing" 的当前 git 版本标识

#### Scenario: 存量 content-hash base 升级不误判 drift
- **WHEN** 升级前以 content-hash 记录了 `base_version` 的 `(agent, skill)` 在升级后首次物化、且其 home 副本未实际改动
- **THEN** 不被误判为 drift，且 `base_version` 被 re-baseline 为 git 标识

#### Scenario: re-baseline 后按 git 标识判定
- **WHEN** re-baseline 完成后该 `(agent, skill)` 再次物化
- **THEN** drift 判定基于 home 副本内容与池中该 git 版本的内容是否一致
