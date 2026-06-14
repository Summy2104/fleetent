## MODIFIED Requirements

### Requirement: materialize 记录 base_version

materialize 覆盖某 agent 的 skill 副本时 SHALL 在 `agent_skills.base_version` 记录该副本物化自的**池 skill 目录内容 hash（sha256）**。pool git sha 另由 `skills.current_version`（catalog 指针）单独跟踪；`base_version` 始终为内容 hash，不含 git 标识，以保证 drift 判定（home 内容是否被改动）正确——pool 自身更新不会触发误判。存量 content-hash `base_version` 无需过渡：格式不变，语义相同，首次物化直接 re-baseline 为当前内容 hash。

#### Scenario: 部署写入内容 hash base_version
- **WHEN** agent "support-bot" 的 skill "billing"（未漂移）被 materialize 刷新
- **THEN** `agent_skills` 中该行的 `base_version` 更新为池中 "billing" 目录当前内容的 sha256 hash（64 hex 字符）

#### Scenario: pool 更新后重新物化不误判 drift
- **WHEN** pool skill "billing" 被更新（v1→v2），agent home 副本仍为 v1（未被 agent 修改）
- **THEN** 再次 materialize 检测 home_hash == base_version（均为 v1 hash）→ not drifted → 正常覆盖为 v2

#### Scenario: agent 修改 home 副本后判定 drift
- **WHEN** agent 修改了其 home 下 skill "crm-ops" 副本，re-materialize 运行
- **THEN** home_hash != base_version → drift=1 → home 副本被保留不覆盖
