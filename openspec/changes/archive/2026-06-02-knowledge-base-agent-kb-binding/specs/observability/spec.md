## ADDED Requirements

### Requirement: Knowledge-base scope diagnostics
系统 SHALL 对 agent KB 范围解析失败或降级记录可诊断事件，帮助 Pilot 环境排查配置问题。

#### Scenario: Default KB missing is diagnostic
- **WHEN** agent 没有显式 KB 绑定
- **AND** 默认 KB 未配置、为空或不可用
- **THEN** 系统记录一条知识库范围诊断事件
- **AND** 事件包含 `tenant_id`、`agent_id` 和原因

#### Scenario: Scope diagnostics avoid sensitive content
- **WHEN** 系统记录知识库范围诊断事件
- **THEN** 事件不包含完整用户 query、文档正文、connector credential、token 或 secret
