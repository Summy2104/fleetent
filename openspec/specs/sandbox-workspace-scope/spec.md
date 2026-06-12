# sandbox-workspace-scope Specification

## Purpose
TBD - created by archiving change sandbox-workspace-scope-split. Update Purpose after archive.
## Requirements
### Requirement: workspace_scope 只控制数据隔离粒度

沙箱生命周期层 SHALL 提供独立的数据隔离粒度选择 `workspace_scope`,取值 `session`(默认)或 `agent`,且其语义 SHALL **仅限于数据隔离**——决定容器名 key、workspace 宿主目录 key、以及容器存活归属(进程隔离边界)。`workspace_scope` MUST NOT 影响依赖镜像的持久化或复用(镜像由独立的 per-agent 镜像持久化开关控制,见 `sandbox-image-persistence`)。同一 `workspace_scope` + 同一归属 key 的请求 MUST 解析到同一容器名与同一 workspace 宿主目录;不同 key MUST 解析到相互隔离的容器与目录。

#### Scenario: workspace_scope 默认 session
- **WHEN** 配置未显式指定 `workspace_scope`,沙箱生命周期层为某会话取得容器
- **THEN** 该容器以 `session` 数据隔离粒度创建,容器名 key 与 workspace 宿主目录 key 均由该会话归属派生

#### Scenario: workspace_scope 不参与镜像选择
- **WHEN** 在 `session` 与 `agent` 两种 `workspace_scope` 下分别取得容器,且 per-agent 镜像持久化开关状态相同
- **THEN** 两次取得容器所用的基础/依赖镜像选择结果一致,即镜像选择不因 `workspace_scope` 不同而改变

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

### Requirement: 删除 agent 作为数据隔离档后的隔离保证

拆出镜像持久化维度后,`agent` 数据隔离档 SHALL NOT 再作为多用户部署的可选项存在;在任何多用户部署中,同一 agent 服务的两个不同会话 MUST 取得相互隔离的容器与 workspace 宿主目录,一方在容器或 workspace 内产生的状态对另一方 MUST NOT 可见。原 `agent` scope「同一 agent 下所有会话共享一个容器/目录」的数据隔离行为 MUST 在多用户部署中被消除。

#### Scenario: 多用户下同 agent 异 session 相互隔离
- **WHEN** 多用户部署中,同一 agent 服务的两个不同会话分别取得沙箱容器
- **THEN** 两者得到名称不同、相互隔离的容器与不同的 workspace 宿主子目录,一方写入 `/workspace` 或容器内的内容对另一方不可见

#### Scenario: 原 agent 共享行为不复现
- **WHEN** 多用户部署中,用户 A 在其会话向 `/workspace` 写入文件后,用户 B 在同一 agent 的另一会话取得容器
- **THEN** 用户 B 的容器 `/workspace` 中不出现用户 A 写入的文件(原 agent scope 跨会话共享目录的行为不再发生)

