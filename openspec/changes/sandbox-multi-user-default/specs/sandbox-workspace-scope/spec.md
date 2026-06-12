## MODIFIED Requirements

### Requirement: 多用户场景强制 session 数据隔离

当部署为多用户(同一 agent 服务多个终端用户,如共享 IM 入口)时,沙箱生命周期层 SHALL 强制 `workspace_scope` 为 `session`。若配置显式声明 `workspace_scope: agent` 而运行形态为多用户,系统 MUST 在启动期将其纠正为 `session` 并记录一条告警,MUST NOT 静默接受 `agent` 数据隔离(否则同一 agent 下所有用户共享一个 workspace 宿主目录与一个容器,构成跨用户数据泄露)。

运行形态(是否多用户)SHALL 由显式配置信号 `sandbox.multi_user`(bool)承载,沙箱管理器在启动期据此驱动上述纠正。该信号 **默认为 `true`(fail-safe)**:每个 agent 默认按多用户处理,跨用户隔离护栏默认在线,任何配置的 `workspace_scope: agent` 默认被纠正为 `session`。仅当部署确知为单用户(single-tenant)、需 agent-scope 跨会话数据复用时,SHALL 显式声明 `sandbox.multi_user: false` 退回单用户行为(opt-out)。该信号 MUST 真正接入管理器构造,默认值不得使护栏失效为永不触发。

#### Scenario: 默认即 fail-safe(未声明 multi_user 时多用户隔离)
- **WHEN** agent.yaml 未声明 `sandbox.multi_user`(取默认 `true`)且配置声明 `workspace_scope: agent`
- **THEN** 生效的 `workspace_scope` 为 `session`,并记录一条「多用户下 agent 数据隔离被纠正为 session」告警(默认无需任何配置即每用户隔离)

#### Scenario: 多用户配 agent 被纠正为 session
- **WHEN** 运行形态为多用户(`sandbox.multi_user: true`,或未声明取默认)且配置声明 `workspace_scope: agent`
- **THEN** 生效的 `workspace_scope` 为 `session`,并记录一条「多用户下 agent 数据隔离被纠正为 session」告警

#### Scenario: 显式 opt-out 后单用户 agent 数据隔离保留
- **WHEN** 配置显式声明 `sandbox.multi_user: false`(单用户 single-tenant)且声明 `workspace_scope: agent`
- **THEN** 生效的 `workspace_scope` 为 `agent`,该 agent 跨会话复用同一数据隔离目录(显式确认单用户、无跨用户泄露面)

#### Scenario: multi_user 信号经配置接入管理器
- **WHEN** 沙箱管理器在 `fleetent agent run` 启动期被构造,agent.yaml 未声明 `multi_user`
- **THEN** 管理器以 `multi_user=true`(默认)构造,护栏对配置的 `agent` workspace_scope 生效纠正;仅当显式 `sandbox.multi_user: false` 时以 `multi_user=false` 构造、配置的 scope 不被纠正
