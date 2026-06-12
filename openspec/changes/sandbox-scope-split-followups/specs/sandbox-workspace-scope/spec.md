## MODIFIED Requirements

### Requirement: 多用户场景强制 session 数据隔离

当部署为多用户(同一 agent 服务多个终端用户,如共享 IM 入口)时,沙箱生命周期层 SHALL 强制 `workspace_scope` 为 `session`。若配置显式声明 `workspace_scope: agent` 而运行形态为多用户,系统 MUST 在启动期将其纠正为 `session` 并记录一条告警,MUST NOT 静默接受 `agent` 数据隔离(否则同一 agent 下所有用户共享一个 workspace 宿主目录与一个容器,构成跨用户数据泄露)。

运行形态(是否多用户)SHALL 由**显式配置信号**决定,而非靠运行时推断:配置项 `sandbox.multi_user`(bool,默认 `false`)承载该信号,沙箱管理器在启动期据此驱动上述纠正。standalone `fleetent agent run` 默认单用户(`multi_user=false`,配置未声明时取默认);platform 托管的多用户共享 agent SHALL 在其 agent.yaml 写入 `sandbox.multi_user: true`(纯配置,不引入 agent 运行时对 platform 的反向依赖)。该信号 MUST 真正接入管理器构造(默认 `false` 时不得使护栏失效为永不触发)。

#### Scenario: 多用户配 agent 被纠正为 session
- **WHEN** 运行形态为多用户(`sandbox.multi_user: true`)且配置声明 `workspace_scope: agent`
- **THEN** 生效的 `workspace_scope` 为 `session`,并记录一条「多用户下 agent 数据隔离被纠正为 session」告警

#### Scenario: 单用户 agent 数据隔离保留
- **WHEN** 运行形态为单用户(single-tenant standalone agent,`sandbox.multi_user` 未声明或为 `false`)且配置声明 `workspace_scope: agent`
- **THEN** 生效的 `workspace_scope` 为 `agent`,该 agent 跨会话复用同一数据隔离目录(单用户下无跨用户泄露面)

#### Scenario: multi_user 信号经配置接入管理器
- **WHEN** agent.yaml 声明 `sandbox.multi_user: true`,沙箱管理器在 `fleetent agent run` 启动期被构造
- **THEN** 管理器以 `multi_user=true` 构造,护栏对配置的 `agent` workspace_scope 生效纠正;未声明时以 `multi_user=false` 构造,配置的 scope 不被纠正
