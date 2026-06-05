## MODIFIED Requirements

### Requirement: 两维迭代预算

主循环 SHALL 在两个维度上度量并约束单次任务的预算：执行步数、token 用量。当任一维度达到其配置上限时，预算判定 MUST 认定预算耗尽。每个维度的上限 MUST 可通过参数注入或当前 agent 的配置（`agent.yaml` 的 `agent_max_turns` / `agent_max_tokens`）覆盖默认值，配置来源 MUST 为 per-agent 配置而非全局 `Settings`；未配置时其默认值 MUST 等于原 `Settings` 默认（步数 50、token 无上限）。每维度 MUST 支持「该维度无上限」。解析优先级 MUST 为：参数注入 > agent 配置 > 字段默认。

#### Scenario: 步数维度达上限触发预算耗尽
- **WHEN** 任务执行步数达到配置的步数上限
- **THEN** 预算判定认定预算耗尽，并可报出触发维度为步数

#### Scenario: token 维度达上限触发预算耗尽
- **WHEN** 累计 token 用量达到配置的 token 上限
- **THEN** 预算判定认定预算耗尽，触发维度为 token

#### Scenario: 步数上限来自 agent 配置
- **WHEN** 某 agent 的 `agent.yaml` 声明 `agent_max_turns: 30`，运行时未注入 `max_turns` 参数
- **THEN** 该次运行的步数上限为 30

#### Scenario: 无上限维度不触发
- **WHEN** 某维度配置为无上限
- **THEN** 该维度的累计用量无论多大都不触发预算耗尽
