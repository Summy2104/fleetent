# platform-read-projection Delta

## ADDED Requirements

### Requirement: agent 侧数据读投影经 name→id 解析（读翻译边界）
agent 侧物理产物（traces、sessions 等）以 agent **name** 标 agent（身份模型 R2）；平台关系层以 `agents.id` 为身份（R1）。故 platform 读 agent 侧 name-keyed 数据并关联回平台 agent 时，SHALL 经 `agents` 表做 **name→id 解析**，且该翻译 SHALL 收口在读投影 / observability 读路径一处，不散落到其它代码。

#### Scenario: 按平台 agent_id 投影其 agent 侧 trace
- **WHEN** platform 投影某 agent（持 `agents.id`）的 trace
- **THEN** 经 `agents` 解析出该 agent 的 name，再按 name 读 agent 侧 traces；结果关联回该 `agents.id`

#### Scenario: 翻译收口
- **WHEN** 审视平台读 agent 侧数据的代码路径
- **THEN** name↔id 翻译只出现在读投影 / observability 读边界（与 materialize 写边界并列的唯二翻译点），不在其它模块重复
