# agent-definition Delta

## ADDED Requirements

### Requirement: Agent name 为不可变标识
`agents.name` SHALL 是创建后不可变的标识符。系统 MUST NOT 提供改名能力（store / admin API / console 均无 rename 路径）——`agent_admin_state`（部署态键）、`session_meta.agent_name`（playground 归属）与 **per-agent 物理数据目录 `agents/<name>/data/`**（agent_state.db / 会话 / 向量的家）均以名字为键，改名会使部署态与历史会话失联、并令 agent 解析到空数据目录（全部运行数据被孤儿）。改名诉求 SHALL 以"创建新 agent + 按需显式迁移数据"满足。

#### Scenario: 无 rename 写路径
- **WHEN** 检查 `agent_store`、`agent_admin_store` 与 agent console API
- **THEN** 不存在修改 `agents.name` 的函数或端点

#### Scenario: 名字键 satellite 的一致性由不可变性保证
- **WHEN** agent 创建后正常运行任意时长
- **THEN** `agent_admin_state`、`session_meta` 与物理目录所用的名字键始终与 `agents.name` 一致（因其不可变）
